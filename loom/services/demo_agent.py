"""Generate a demo site, then hold it to account before anyone sees it.

A single Claude call produces a plausible page. The failure that matters isn't
ugly output — it's a page that looks perfect and quietly invents a $18 burger
the shop doesn't sell. You cannot send that to a business owner.

So generation runs as a loop:

    pre-flight   drop image URLs that don't actually load
    draft        Claude writes the page
    check        deterministic rules, no model involved
    repair       violations go back with the exact list; regenerate
    (repeat, bounded)

The checks are deliberately mechanical rather than a model critique. "Does
every price in this HTML appear in the harvest" is a set operation with a
correct answer; asking a model to judge it would reintroduce the very failure
mode being tested for.
"""

import asyncio
import re
from html import unescape

import httpx
from pydantic import BaseModel, Field

from loom.llm.client import Claude, Model
from loom.services.demo_builder import build_html, extract_document
from loom.services.demo_render import render_demo
from loom.services.render_check import render_check, screenshot
from loom.services.site_harvest import Harvest

MAX_ROUNDS = 2
IMAGE_CHECK_TIMEOUT = 6.0
IMAGE_CHECK_CONCURRENCY = 6

_IMG_SRC_RE = re.compile(r"<img\b[^>]*?src=[\"']([^\"']+)[\"']", re.I)
_EXTERNAL_SCRIPT_RE = re.compile(r"<script\b[^>]*\bsrc=[\"']https?://", re.I)
_ANY_SCRIPT_RE = re.compile(r"<script\b", re.I)
_EXTERNAL_STYLE_RE = re.compile(
    r"<link\b[^>]*\bhref=[\"']https?://[^\"']*[\"'][^>]*rel=[\"']stylesheet|"
    r"<link\b[^>]*rel=[\"']stylesheet[\"'][^>]*\bhref=[\"']https?://",
    re.I,
)
_IMPORT_RE = re.compile(r"@import\s+url\(\s*[\"']?https?://", re.I)
_NOINDEX_RE = re.compile(r"<meta[^>]+name=[\"']robots[\"'][^>]+noindex", re.I)
_VIEWPORT_RE = re.compile(r"<meta[^>]+name=[\"']viewport[\"']", re.I)
# Currency amounts as a shop would write them: $4, $4.50, 4.50, AUD 12
_PRICE_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)")
_TAG_RE = re.compile(r"<[^>]+>")


class Violation(BaseModel):
    code: str
    detail: str


class DemoResult(BaseModel):
    html: str = ""
    rounds: int = 0
    fixed: list[str] = Field(default_factory=list)
    remaining: list[Violation] = Field(default_factory=list)
    dropped_images: list[str] = Field(default_factory=list)
    rendered: bool = False
    render_skipped: str | None = None
    # True when the business had no photographs and placeholders were used.
    used_stock: bool = False
    # "template" when rendered, "model" when generated.
    engine: str = "model"
    # JPEG of the page at phone width — the hook for the approach email.
    thumb: bytes | None = Field(default=None, repr=False, exclude=True)

    @property
    def ok(self) -> bool:
        return bool(self.html) and not self.remaining


async def live_images(urls: list[str]) -> tuple[list[str], list[str]]:
    """Split image URLs into ones that actually load and ones that don't.

    Worth the round trips: a CDN URL scraped with the wrong size parameter
    renders as a broken icon, and a demo with broken images is worse than a
    demo with none.
    """
    if not urls:
        return [], []
    gate = asyncio.Semaphore(IMAGE_CHECK_CONCURRENCY)

    async def check(client: httpx.AsyncClient, url: str) -> tuple[str, bool]:
        async with gate:
            try:
                response = await client.get(url, headers={"Range": "bytes=0-2048"})
                ok = response.status_code < 400 and response.headers.get(
                    "content-type", ""
                ).startswith("image/")
                return url, ok
            except httpx.HTTPError:
                return url, False

    async with httpx.AsyncClient(
        timeout=IMAGE_CHECK_TIMEOUT, follow_redirects=True
    ) as client:
        results = await asyncio.gather(*(check(client, u) for u in urls))

    return [u for u, ok in results if ok], [u for u, ok in results if not ok]


def check_html(
    html: str, harvest: Harvest, *, stock_used: bool = False
) -> list[Violation]:
    """Everything that can be decided without asking a model."""
    problems: list[Violation] = []
    if not html or len(html) < 500:
        problems.append(Violation(code="empty", detail="the page is essentially empty"))
        return problems
    if html.lstrip().startswith("```"):
        problems.append(
            Violation(code="fenced", detail="output is wrapped in a markdown fence")
        )
    if not html.lower().lstrip().startswith(("<!doctype", "<html")):
        problems.append(
            Violation(
                code="preamble",
                detail="the output must begin with <!doctype html>; strip any commentary before it",
            )
        )
    if "<body" not in html.lower():
        problems.append(Violation(code="no_body", detail="no <body> element"))
    if not _NOINDEX_RE.search(html):
        problems.append(
            Violation(
                code="missing_noindex",
                detail='add <meta name="robots" content="noindex, nofollow"> to the head',
            )
        )
    if not _VIEWPORT_RE.search(html):
        problems.append(
            Violation(code="missing_viewport", detail="add the viewport meta tag")
        )
    if _EXTERNAL_SCRIPT_RE.search(html):
        problems.append(
            Violation(code="external_script", detail="remove the external <script src>")
        )
    elif _ANY_SCRIPT_RE.search(html):
        # A brochure page needs no JavaScript, and the public route serves
        # these under a CSP that blocks scripts anyway — so a script tag is
        # dead weight that would silently not run.
        problems.append(
            Violation(
                code="script_tag",
                detail="remove the <script> block; the page must work without JavaScript",
            )
        )
    if _EXTERNAL_STYLE_RE.search(html) or _IMPORT_RE.search(html):
        problems.append(
            Violation(
                code="external_stylesheet",
                detail="inline the CSS; no external stylesheet or @import",
            )
        )

    # Images must come from the supplied set — anything else is a stock photo
    # the model reached for, which would ship someone else's picture.
    allowed = set(harvest.selection.images_from(harvest.images))
    for raw_src in _IMG_SRC_RE.findall(html):
        # An attribute is HTML-escaped, so a correctly written &amp; is the
        # same URL as the & in the allow list. Comparing raw strings flagged
        # every templated image as unknown.
        src = unescape(raw_src)
        if src.startswith("data:"):
            continue
        if src not in allowed:
            problems.append(
                Violation(
                    code="unknown_image",
                    detail=f"image not in the supplied set: {src[:90]}",
                )
            )

    # Safari — which is what an iPhone-owning shop keeper is holding — still
    # requires the prefix. Without it the glass silently renders as a flat
    # translucent box on the one device that matters most.
    if "backdrop-filter" in html and "-webkit-backdrop-filter" not in html:
        problems.append(
            Violation(
                code="unprefixed_backdrop_filter",
                detail="add -webkit-backdrop-filter alongside every backdrop-filter, or it won't render on Safari/iOS",
            )
        )

    # A preview with no way to reply is wasted work, and an unattributed page
    # carrying someone else's name and photos is worse than wasted.
    from loom.services.demo_defaults import attribution_email

    email = attribution_email()
    if email and email.lower() not in html.lower():
        problems.append(
            Violation(
                code="missing_attribution",
                detail=f"the closing block must name the sender and include {email}",
            )
        )

    # Placeholder photography must be declared. Without the note the owner
    # could reasonably think we are showing their premises back to them.
    if stock_used:
        from loom.services.demo_defaults import stock_note

        note = stock_note()
        if note and note.lower() not in html.lower():
            problems.append(
                Violation(
                    code="missing_stock_note",
                    detail=f'the page must carry the line "{note}" near the images',
                )
            )

    # The one that matters: no price may appear that isn't in the harvest.
    menu = harvest.selection.menu_from(harvest.menu)
    known = {
        m.group(1)
        for item in menu
        if item.price
        for m in _PRICE_RE.finditer(item.price)
    }
    text = _TAG_RE.sub(" ", html)
    for match in _PRICE_RE.finditer(text):
        if match.group(1) not in known:
            problems.append(
                Violation(
                    code="invented_price",
                    detail=f"${match.group(1)} appears on the page but not in the harvest",
                )
            )
    return problems


async def _all_problems(
    html: str, harvest: Harvest, result: "DemoResult"
) -> list[Violation]:
    """Static rules plus what a browser sees when it actually renders the page.

    Reading the HTML can't tell you the layout blows out on a phone, and that
    is the exact fault these demos exist to fix elsewhere.
    """
    problems = check_html(html, harvest, stock_used=result.used_stock)
    report = await render_check(html)
    if report.skipped:
        result.render_skipped = report.skipped
    else:
        result.rendered = True
        problems += [
            Violation(code=p["code"], detail=p["detail"]) for p in report.problems
        ]
    return problems


REPAIR_SYSTEM = """You are fixing a single-page website you produced earlier.

Return ONLY the corrected, complete HTML document — no markdown fence, no
commentary, no partial diff.

Fix exactly the listed problems and change nothing else. In particular, never
resolve a problem by inventing content: if a price or an image is flagged as
unsupported, delete it rather than substitute another."""


async def build_variants(
    lead: dict,
    harvest: Harvest,
    *,
    directions: list[str] | None = None,
    count: int = 3,
    claude: Claude | None = None,
) -> dict[str, DemoResult]:
    """Build several designs of the same page, one per art direction.

    Choosing a direction from the trade alone is a guess at the owner's taste.
    Three to compare costs about a dollar and removes the guess.

    Each variant runs its own check-and-repair loop: one design tripping a
    rule must not drag the others down with it, and a failure in one is
    reported rather than aborting the set.
    """
    from loom.services.demo_defaults import pick_direction, styles

    available = list(styles().get("directions", {}))
    if not available:
        result = await build_demo(lead, harvest, claude=claude)
        return {"default": result}

    if directions:
        # A reviewed plan decides; anything unknown is dropped rather than
        # silently swapped for a default.
        chosen = [d for d in directions if d in available]
    else:
        # No plan — fall back to the trade's default, padded for contrast.
        preferred, _ = pick_direction(lead.get("primary_type"))
        chosen = ([preferred] + [d for d in available if d != preferred])[:count]
    if not chosen:
        return {}

    shared = claude or Claude.tracked("demo_build")

    async def one(direction: str) -> tuple[str, DemoResult]:
        try:
            return direction, await build_demo(
                lead, harvest, claude=shared, style=direction
            )
        except Exception as e:  # a bad variant must not sink the set
            failed = DemoResult()
            failed.remaining = [
                Violation(code="generation_failed", detail=str(e)[:200])
            ]
            return direction, failed

    results = await asyncio.gather(*(one(d) for d in chosen))
    return {d: r for d, r in results if r.html or r.remaining}


async def build_demo(
    lead: dict,
    harvest: Harvest,
    *,
    claude: Claude | None = None,
    max_rounds: int = MAX_ROUNDS,
    style: str | None = None,
) -> DemoResult:
    """Draft, check, repair. Returns the best page reached and what's left."""
    claude = claude or Claude.tracked("demo_build")
    result = DemoResult()

    # Pre-flight: a dead image URL can't be fixed by regenerating, so prune
    # before the model ever sees the list.
    usable, dead = await live_images(
        harvest.selection.images_from(harvest.images)
    )
    result.dropped_images = dead
    working = harvest.model_copy(deep=True)
    working.images = usable
    working.selection.images = [i for i in working.selection.images if i in usable]

    # A business with no photographs of its own still needs a page that looks
    # finished. Their FACTS stay theirs; the pictures are set dressing, and
    # the page says so in as many words. Putting them on the harvest is what
    # also makes check_html accept them — anything outside this set is still
    # a stock photo the model reached for on its own.
    if not working.images:
        from loom.services.demo_defaults import stock_images

        candidates = stock_images(lead.get("primary_type"))
        if candidates:
            live, _ = await live_images(candidates)
            working.images = live
            working.selection.images = []
            result.used_stock = bool(live)

    # A hand-written template renders the same correct page every time; the
    # model is the fallback for directions that don't have one yet. The
    # checker runs over both, so the two paths are held to one standard.
    templated = render_demo(style, lead, working, stock_used=result.used_stock) if style else None
    if templated:
        result.html = templated
        result.engine = "template"
        result.rounds = 0
        result.remaining = await _all_problems(templated, working, result)
        result.thumb = await screenshot(templated)
        return result

    html = await build_html(lead, working, claude=claude, style=style)
    result.rounds = 1
    problems = await _all_problems(html, working, result)

    for _ in range(max_rounds):
        if not problems:
            break
        listing = "\n".join(f"- [{p.code}] {p.detail}" for p in problems)
        html = await claude.complete(
            f"Problems found in the page:\n{listing}\n\n"
            f"Here is the current HTML:\n\n{html}",
            model=Model.SONNET,
            system=REPAIR_SYSTEM,
            max_tokens=16000,
        )
        html = extract_document(html)
        result.rounds += 1
        before = {p.code for p in problems}
        problems = await _all_problems(html, working, result)
        result.fixed += sorted(before - {p.code for p in problems})

    result.html = html
    result.remaining = problems
    result.thumb = await screenshot(html)
    return result
