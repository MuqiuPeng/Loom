"""Decide which designs are worth building, before building any.

Generating a full set and letting the good one be picked afterwards works, but
it pays for every direction that was never plausible — and with a dozen
directions to choose from, most of them aren't. Reading the harvest first
costs one cheap call and turns the expensive step into a decision.

The output is deliberately a proposal, not an instruction: it comes back to
the panel with reasons attached, gets adjusted, and only then does anything
get generated.
"""

from typing import Any

from pydantic import BaseModel, Field

from loom.llm.client import Claude, Model
from loom.services.demo_defaults import styles
from loom.services.site_harvest import Harvest


class DirectionPick(BaseModel):
    direction: str
    fit: int = 0  # 0-100
    why: str = ""


class DemoPlan(BaseModel):
    """What the business looks like, and which designs suit it."""

    read: str = ""  # one line on what kind of business this appears to be
    picks: list[DirectionPick] = Field(default_factory=list)
    rejected: list[DirectionPick] = Field(default_factory=list)
    angle: str = ""  # the thing the page should lead on
    caution: str = ""  # anything thin or missing that will limit the result
    error: str | None = None

    @property
    def chosen(self) -> list[str]:
        return [p.direction for p in self.picks]


SYSTEM = """You choose art directions for a mock website built to win a small
business as a client. Return ONLY JSON.

You are given: the business name, its trade, what was harvested from its own
site, and the catalogue of available directions with the rules each imposes.

Schema:
{
  "read": str,          // one sentence: what kind of business this appears to be, from the evidence
  "picks": [{"direction": str, "fit": int, "why": str}],   // 3-4, best first, fit 0-100
  "rejected": [{"direction": str, "fit": int, "why": str}],// 2-3 worth naming, with the reason
  "angle": str,         // the single thing the page should lead on
  "caution": str        // what's thin in the data and will limit the result; "" if nothing
}

How to choose:
- Pick for CONTRAST as well as fit. Three variations on one idea give the owner
  nothing to decide between; one safe, one characterful and one adventurous is
  a real choice.
- Judge from evidence, not the trade label. A roastery selling single-origin
  beans online is not the same business as a suburban milk-bar cafe, even
  though Google calls both "cafe".
- Weigh what the harvest actually contains. A direction whose rules depend on
  photography is a poor pick for a business with none.
- `why` must cite something specific — a menu item, the tone of their about
  text, the absence of a website. Never generic praise.
- `angle` is what a person would notice first walking past. If the data is too
  thin to know, say so plainly rather than inventing something.
- Never invent facts about the business anywhere in this output."""


def _catalogue() -> str:
    lines = []
    for key, direction in styles().get("directions", {}).items():
        rules = direction.get("rules", [])
        lines.append(
            f"- {key} ({direction.get('label', key)}): "
            f"suits {', '.join(direction.get('suits', [])) or 'anything'}. "
            f"{rules[0] if rules else ''}"
        )
    return "\n".join(lines)


def _evidence(lead: dict, harvest: Harvest) -> str:
    lines = [
        f"Business name: {lead.get('google_name') or lead.get('site_title') or 'unknown'}",
        f"Google category: {lead.get('primary_type') or 'unknown'}",
        f"Their site: {lead.get('site_url') or 'none — they have no website'}",
    ]
    extra = lead.get("google_extra") or {}
    if extra.get("google_rating"):
        lines.append(
            f"Google rating: {extra['google_rating']} "
            f"from {extra.get('google_rating_count', '?')} reviews"
        )
    if extra.get("google_price_level"):
        lines.append(f"Price level: {extra['google_price_level']}")
    if extra.get("google_types"):
        lines.append(f"All categories: {', '.join(extra['google_types'][:8])}")

    audit = lead.get("audit") or {}
    findings = audit.get("findings") or []
    if findings:
        lines.append(
            "What's wrong with their web presence: "
            + "; ".join(f.get("label", "") for f in findings)
        )

    lines.append(f"Site title as written: {harvest.about or lead.get('site_title') or '—'}")
    lines.append(f"Pages read: {len(harvest.pages_read)}")
    lines.append(f"Photographs of their own: {len(harvest.images)}")
    lines.append(f"Menu items found: {len(harvest.menu)}")
    if harvest.menu:
        lines.append(
            "Sample of the menu: "
            + "; ".join(
                f"{m.name}{' ' + m.price if m.price else ''}" for m in harvest.menu[:12]
            )
        )
    if harvest.hours:
        lines.append(f"Hours: {harvest.hours}")
    if harvest.socials:
        lines.append(f"Socials: {', '.join(harvest.socials)}")
    return "\n".join(lines)


async def plan_demo(
    lead: dict, harvest: Harvest, *, claude: Claude | None = None
) -> DemoPlan:
    """Read the evidence and propose directions. Cheap; nothing is generated."""
    claude = claude or Claude.tracked("demo_plan")
    available = set(styles().get("directions", {}))

    try:
        # DemoPlan is the tool schema, so shape and types are enforced by the
        # API rather than reconstructed field by field afterwards.
        plan = await claude.extract_model(
            f"EVIDENCE\n{_evidence(lead, harvest)}\n\n"
            f"AVAILABLE DIRECTIONS\n{_catalogue()}",
            DemoPlan,
            model=Model.SONNET,
            system=SYSTEM,
        )
    except Exception as e:
        return DemoPlan(error=str(e)[:200])

    # Still checked by hand: the schema can enforce "a string" but not "one of
    # the twelve directions that exist". An invented name would fail silently
    # at build time.
    plan.picks = [p for p in plan.picks if p.direction in available]
    plan.rejected = [p for p in plan.rejected if p.direction in available]
    return plan


def as_dict(plan: DemoPlan) -> dict[str, Any]:
    return plan.model_dump(mode="json")
