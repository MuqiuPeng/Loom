"""Answer "which town is worth working" with numbers rather than a hunch.

Choosing where to prospect matters more than anything done afterwards: in a
mature market the good operators already have good sites and the bad ones are
coasting on regulars. The reverse — a visitor town where strangers pick a
restaurant off Google Maps before walking in — is where a broken site actually
costs the owner a table tonight.

A survey scans several areas the same way a real search does, then reports the
aggregate: how many have no site at all, how many have a site with something
demonstrably wrong, and how strong the buying signals look. One run, then work
the top of the list.

Rendering is deliberately off here. Opening a headless browser on every site in
ten towns costs minutes for a number that barely moves the ranking; the leads
you then pursue get the full treatment.
"""

import asyncio
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from loom.services.company_scout import Candidate, scout

CONFIG_PATH = Path("config/scout_areas.json")
DEFAULT_LIMIT = 20
CONCURRENT_AREAS = 3


EMPTY_CONFIG: dict[str, Any] = {"countries": {}, "default_survey": []}


@lru_cache(maxsize=1)
def _load(mtime: float) -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(EMPTY_CONFIG)


def areas_config() -> dict[str, Any]:
    try:
        return _load(CONFIG_PATH.stat().st_mtime)
    except OSError:
        return dict(EMPTY_CONFIG)


def suggested_areas() -> list[dict[str, str]]:
    """Every curated area, flattened, with its reason attached.

    Each entry carries the country it belongs to and the provider that can
    answer for it, so a caller can tell an area it can search from one that is
    research for a market not wired up yet.
    """
    out: list[dict[str, str]] = []
    for code, country in areas_config().get("countries", {}).items():
        for region, entries in (country.get("regions") or {}).items():
            for entry in entries:
                out.append(
                    {
                        **entry,
                        "region": region,
                        "country": code,
                        "country_name": country.get("name", code),
                        "provider": country.get("provider", "google"),
                        "language": country.get("language"),
                    }
                )
    return out


def country_of(area: str) -> str | None:
    """Which country a curated area sits in, if it is one we know."""
    for entry in suggested_areas():
        if entry["area"] == area:
            return entry.get("country")
    return None


def searchable_countries() -> list[dict[str, Any]]:
    """Countries in the config, and whether a provider can actually serve them."""
    from loom.services.places import ProviderUnavailableError, provider_for

    out = []
    for code, country in areas_config().get("countries", {}).items():
        try:
            provider_for(code, named=country.get("provider"))
            available = True
            detail = None
        except ProviderUnavailableError as e:
            available = False
            detail = str(e)
        out.append(
            {
                "code": code,
                "name": country.get("name", code),
                "provider": country.get("provider", "google"),
                "available": available,
                "detail": detail,
                "areas": sum(len(v) for v in (country.get("regions") or {}).values()),
            }
        )
    return out


class AreaResult(BaseModel):
    area: str
    note: str = ""
    total: int = 0
    no_website: int = 0
    broken_site: int = 0  # has a site, and the audit found something
    workable: int = 0  # a real problem AND a plausible buyer
    contactable: int = 0  # at least one published email
    avg_signal: int = 0
    top: list[str] = Field(default_factory=list)
    error: str | None = None

    @property
    def hit_rate(self) -> float:
        """Share of the businesses here that are worth approaching."""
        return round(100 * self.workable / self.total, 1) if self.total else 0.0


def _summarise(area: str, note: str, found: list[Candidate]) -> AreaResult:
    workable = [c for c in found if c.opportunity >= 3 and c.signal >= 40]
    return AreaResult(
        area=area,
        note=note,
        total=len(found),
        no_website=sum(1 for c in found if not c.has_website),
        broken_site=sum(1 for c in found if c.has_website and c.opportunity >= 3),
        workable=len(workable),
        contactable=sum(1 for c in found if c.emails),
        avg_signal=round(sum(c.signal for c in found) / len(found)) if found else 0,
        top=[c.google_name for c in sorted(workable, key=lambda c: -c.priority)[:3]],
    )


async def survey(
    query: str,
    areas: list[str] | None = None,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[AreaResult]:
    """Scan each area and rank them by how many workable leads they hold."""
    notes = {a["area"]: a.get("note", "") for a in suggested_areas()}
    targets = areas or areas_config().get("default_survey", [])
    if not targets:
        return []

    gate = asyncio.Semaphore(CONCURRENT_AREAS)

    known = {a["area"]: a for a in suggested_areas()}

    async def one(area: str) -> AreaResult:
        async with gate:
            try:
                entry = known.get(area, {})
                found = await scout(
                    query, near=area, max_results=limit, enrich=True, render=False,
                    country=entry.get("country"), provider=entry.get("provider"),
                )
            except Exception as e:
                return AreaResult(area=area, note=notes.get(area, ""), error=str(e)[:160])
            return _summarise(area, notes.get(area, ""), found)

    results = await asyncio.gather(*(one(a) for a in targets))
    # Rank on workable leads, then on how reachable they are — a town full of
    # broken sites with no published addresses is a week of phone calls.
    return sorted(results, key=lambda r: (-r.workable, -r.contactable))
