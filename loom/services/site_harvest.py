"""Pull everything a demo site would need out of a business's own web presence.

The audit in site_audit.py answers "is something wrong here". This answers
"what do they actually sell" — the material a mock-up has to be built from:
menu with prices, trading hours, address, phone, images, social links.

Two sources, in order of preference:

  * their own website — pages are fetched politely (robots.txt honoured, a
    handful of pages max) and the menu-looking one is handed to Claude, which
    is far better at reading a menu laid out in divs than any regex.
  * their Instagram / Facebook link — for shops with no site at all, that is
    the only place the menu exists. We record the handle; scraping the
    platforms themselves is out of scope and against their terms.

Everything here comes off the business's own pages, so unlike Places data it
carries no storage restriction.
"""

import asyncio
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, Field

from loom.llm.client import Claude, Model
from loom.services.company_scout import (
    USER_AGENT,
    _SiteFetcher,
    _text,
    visible_text,
)
from loom.services.page_render import Renderer, is_thin

MAX_PAGES = 6
# Budgets sized for real page copy. They were set for tag-stripped HTML, which
# on a themed site is ~98% JavaScript — 6k chars of that never reached the
# menu. visible_text() cuts a Shopify page from 73k to 1.5k, so a page now
# fits whole and there is room for more of them.
PAGE_TEXT_CHARS = 12_000
MAX_TEXT_CHARS = 40_000
FETCH_TIMEOUT = 10.0

_WHITESPACE_RE = re.compile(r"\s+")
_MENU_HINT = re.compile(r"menu|food|drink|eat|dine|order|coffee|breakfast|lunch", re.I)
_ABOUT_HINT = re.compile(r"about|contact|find-?us|location|hours|visit", re.I)
_LINK_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_IMG_RE = re.compile(r"<img\b[^>]*?src=[\"']([^\"']+)[\"']", re.I)
# Lazy-loading themes leave src as a 1px placeholder and put the real file in
# a data-* attribute or srcset — the plain src scrape misses every photo.
_LAZY_RE = re.compile(
    r"<img\b[^>]*?(?:data-src|data-original|data-lazy(?:-src)?)=[\"']([^\"']+)[\"']", re.I
)
_SRCSET_RE = re.compile(r"<(?:img|source)\b[^>]*?srcset=[\"']([^\"']+)[\"']", re.I)
# og:image is the picture the business chose to represent itself — usually the
# best single image on the whole site, and it never appears in an <img> tag.
_META_IMG_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](?:og:image(?::secure_url)?|twitter:image)[\"']"
    r"[^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_META_IMG_REV_RE = re.compile(
    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+"
    r"(?:property|name)=[\"'](?:og:image(?::secure_url)?|twitter:image)[\"']",
    re.I,
)
# WordPress/Shopify thumbnail suffixes — the same photo at unusable size.
_THUMB_RE = re.compile(r"[-_]\d{2,3}x\d{2,3}\.(?:jpe?g|png|webp)$", re.I)
_SOCIAL_RE = re.compile(
    r"https?://(?:www\.)?(instagram\.com|facebook\.com|tiktok\.com|x\.com|twitter\.com)/"
    r"([A-Za-z0-9_.\-/]+)",
    re.I,
)
# Sprites, icons and tracking pixels are never usable photography.
_IMG_NOISE = re.compile(
    r"logo|wordmark|submark|brand-?mark|icon|favicon|sprite|pixel|badge|"
    r"placeholder|spacer|blank|loading|avatar|payment|visa|mastercard|paypal|"
    r"staticmap|getmapimage|map-?image",
    re.I,
)
# Characters that cannot occur inside a single URL attribute. Any of them
# means the match ran past the attribute it started in.
_URL_JUNK = ('"', "'", " ", "\\", "\n", "\t", "<", ">")

# Heroes are routinely CSS backgrounds rather than <img> tags.
_CSS_BG_RE = re.compile(r"background(?:-image)?\s*:\s*[^;}]*url\(\s*['\"]?([^'\")]+)", re.I)


class MenuItem(BaseModel):
    name: str = ""
    price: str | None = None
    description: str | None = None
    section: str | None = None


class Selection(BaseModel):
    """What the user picked out of the harvest to actually build with.

    An empty list means "everything" rather than "nothing" — a fresh harvest
    is usable immediately, and curating is an optional narrowing step.
    """

    images: list[str] = Field(default_factory=list)
    menu: list[str] = Field(default_factory=list)  # by item name
    use_hours: bool = True
    use_about: bool = True
    highlight: str | None = None  # anything the user wants the demo to lead on

    def images_from(self, images: list[str]) -> list[str]:
        """The picked images, in the order they were picked.

        Iterating the harvest and testing membership — which is what this did —
        filters correctly and then hands back the harvest's own order, so a
        curated first image silently stops being first. Which image leads is
        most of what a viewer sees; discarding the one signal that says which
        one should is not a small loss.

        Still intersected rather than returned as-is: a selection made before a
        re-harvest can name an image the site no longer serves, and a demo is
        better without that photo than with a broken one.
        """
        if not self.images:
            return images
        available = set(images)
        return [i for i in self.images if i in available]

    def menu_from(self, menu: list["MenuItem"]) -> list["MenuItem"]:
        return [m for m in menu if m.name in self.menu] if self.menu else menu


class Extracted(BaseModel):
    """Exactly what the model is allowed to return.

    Declared separately from Harvest so the tool schema carries only the
    fields a model may fill — pages_read, images and socials are gathered by
    the crawler and must never be model-supplied.
    """

    menu: list[MenuItem] = Field(default_factory=list)
    hours: str | None = None
    address: str | None = None
    phone: str | None = None
    about: str | None = None


class Harvest(BaseModel):
    """Everything gathered about one business, from its own pages."""

    pages_read: list[str] = Field(default_factory=list)
    menu: list[MenuItem] = Field(default_factory=list)
    hours: str | None = None
    address: str | None = None
    phone: str | None = None
    about: str | None = None
    images: list[str] = Field(default_factory=list)
    socials: dict[str, str] = Field(default_factory=dict)
    selection: Selection = Field(default_factory=Selection)
    error: str | None = None

    @property
    def is_usable(self) -> bool:
        """Enough substance to build a demo from."""
        return bool(self.menu or self.about or self.images)


EXTRACT_SYSTEM = """You read a small business's own web pages and pull out the
facts needed to rebuild their site. Return ONLY JSON, no prose.

Schema:
{
  "menu": [{"name": str, "price": str|null, "description": str|null, "section": str|null}],
  "hours": str|null,      // as written, e.g. "Mon-Fri 7am-3pm, Sat-Sun 8am-2pm"
  "address": str|null,
  "phone": str|null,
  "about": str|null       // 1-2 sentences in the business's own voice
}

Rules:
- Copy prices exactly as shown, including the currency symbol.
- "section" is the menu heading an item sits under (Coffee, Breakfast, ...).
- Never invent an item, a price, or an opening hour. If the page doesn't say
  it, use null or an empty list.
- If there is no menu on the page, return an empty menu array."""


# See the note on _TRANSPORT_ERRORS in company_scout: a TLS failure is an
# OSError, not an httpx.HTTPError, and slips straight through the narrower
# clause. A harvest that crashes on a bad certificate takes the whole demo
# build down with it.
_TRANSPORT_ERRORS = (httpx.HTTPError, OSError)


async def _thicken(renderer: Renderer, url: str, html: str) -> str:
    """The rendered document when the fetched one carries no text.

    Checked per page rather than once for the site: a server-rendered home
    page can still link to a menu that is a client-side app, and paying for a
    browser on the pages that do not need one is the cost this avoids.
    """
    if not is_thin(visible_text(html)):
        return html
    return await renderer.html_of(url) or html


def _pick_pages(html: str, base: str) -> list[str]:
    """Choose the few internal pages worth reading, best menu candidate first.

    Ranked rather than first-come: a nav listing "Order Online" before "Menu"
    used to spend the budget on a checkout page and never reach the menu.
    """
    scored: dict[str, int] = {}
    origin = urlparse(base).netloc

    for href, label in _LINK_RE.findall(html):
        url = urljoin(base, href.split("#")[0])
        if not url.startswith(("http://", "https://")):
            continue
        if urlparse(url).netloc != origin or url.rstrip("/") == base.rstrip("/"):
            continue

        path = urlparse(url).path.lower()
        text = _text(label).strip().lower()
        score = 0
        if re.search(r"/menus?/?$|/menus?[-/]", path) or text in {"menu", "menus"}:
            score = 10  # the actual menu page
        elif _MENU_HINT.search(f"{path} {text}"):
            score = 5  # food-adjacent: order online, drinks, breakfast
        elif _ABOUT_HINT.search(f"{path} {text}"):
            score = 2
        if score and score > scored.get(url, 0):
            scored[url] = score

    ranked = sorted(scored.items(), key=lambda kv: -kv[1])
    return [url for url, _ in ranked][: MAX_PAGES - 1]


def _widest(srcset: str) -> str | None:
    """Take the largest candidate out of a srcset."""
    best, best_w = None, -1
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        width = 0
        if len(bits) > 1 and bits[1].endswith("w"):
            width = int(bits[1][:-1]) if bits[1][:-1].isdigit() else 0
        if width >= best_w:
            best, best_w = bits[0], width
    return best


def _declared_size(query: str) -> int:
    """Largest width/height a CDN URL declares, 0 if it declares none.

    Shopify and friends resize through the query string, so the same file
    appears as a 48px favicon and a 2048px hero. The number is the only way to
    tell them apart without fetching.
    """
    sizes = [int(v) for v in re.findall(r"(?:width|height|w|h)=(\d+)", query)]
    return max(sizes) if sizes else 0


def _images(html: str, base: str) -> list[str]:
    """Photographs worth putting in a demo, best first.

    Ordered deliberately: og:image leads because it's the business's own pick
    of hero shot, then lazy-loaded and srcset sources (where themes hide the
    full-size files), then plain <img src>.

    Logos, icons, SVG artwork and CDN thumbnails are dropped — a demo needs
    photography, and a wordmark at 48px is worse than nothing.
    """
    candidates: list[str] = []
    candidates += _META_IMG_RE.findall(html)
    candidates += _META_IMG_REV_RE.findall(html)
    candidates += _LAZY_RE.findall(html)
    candidates += [w for s in _SRCSET_RE.findall(html) if (w := _widest(s))]
    candidates += _IMG_RE.findall(html)
    candidates += _CSS_BG_RE.findall(html)

    # path-without-query → (best declared size, full url), so one photo
    # doesn't occupy four slots at four sizes.
    best: dict[str, tuple[int, str]] = {}
    for src in candidates:
        # Attributes arrive HTML-escaped; &amp; in a URL breaks the request.
        src = unescape(src.strip())
        if not src or src.startswith("data:"):
            continue
        # A quote, a space or a backslash inside what should be one URL means
        # the match ran past the attribute it started in — usually into
        # JavaScript, where the same address appears again inside a string.
        # pvgrinds.com produced exactly that: the captured value began with a
        # quote, urljoin treated the whole thing as a relative path, and the
        # demo was handed
        #     http://pvgrinds.com/"http:/pvgrinds.com/images/...jpg
        # which renders as a broken image in the panel and in the page. That
        # site never finishes rendering, so the browser fallback cannot save
        # it and the raw HTML — scripts and all — is what gets scanned.
        if any(character in src for character in _URL_JUNK):
            continue
        url = urljoin(base, src)
        if not url.startswith(("http://", "https://")):
            continue
        # Two schemes in one address is the same fault seen from the other
        # end: a full URL that has been joined onto a base as though it were
        # a path.
        if url.count("://") > 1:
            continue

        parts = urlparse(url)
        path = parts.path
        if _IMG_NOISE.search(path) or _THUMB_RE.search(path):
            continue
        if not re.search(r"\.(jpe?g|png|webp|avif)$", path, re.I):
            continue  # svg and extensionless endpoints are artwork, not photos

        size = _declared_size(parts.query)
        if 0 < size < 300:
            continue  # an explicit thumbnail or a 1px lazy placeholder

        key = f"{parts.netloc}{path}"
        if key not in best or size > best[key][0]:
            best[key] = (size, url)

    # Preserve discovery order (og:image first), not dict insertion by size.
    seen: list[str] = []
    for _, url in best.values():
        if url not in seen:
            seen.append(url)
    return seen[:12]


def _socials(html: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for host, handle in _SOCIAL_RE.findall(html):
        platform = host.split(".")[0].lower()
        handle = handle.strip("/").split("/")[0]
        # Platform chrome, not the business's own account.
        if handle.lower() in {"sharer", "share", "intent", "profile.php", "p", "tr"}:
            continue
        found.setdefault(platform, handle)
    return found


async def harvest_site(
    url: str, *, business: str = "", claude: Claude | None = None
) -> Harvest:
    """Read a business's site and extract what a demo needs.

    `business` is only used to judge the photographs — whether a picture is
    of this shop or is stock the theme shipped with.
    """
    harvest = Harvest()
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        fetcher = _SiteFetcher(client)
        try:
            home, _ = await fetcher._get(url)
        except _TRANSPORT_ERRORS as e:
            harvest.error = str(e)[:200]
            return harvest
        if home is None or home.status_code >= 400:
            harvest.error = "home page unreadable"
            return harvest

        base = str(home.url)
        # A shell page costs more than the text it is missing: _pick_pages
        # reads its links, so nothing gets crawled either, and the home page
        # is the one where that compounds.
        async with Renderer() as renderer:
            home_html = await _thicken(renderer, base, home.text)

            pages = {base: home_html}
            harvest.pages_read = [base]
            harvest.images = _images(home_html, base)
            harvest.socials = _socials(home_html)

            for page_url in _pick_pages(home_html, base):
                try:
                    response, _ = await fetcher._get(page_url)
                except _TRANSPORT_ERRORS:
                    continue
                if response is None or response.status_code >= 400:
                    continue
                html = await _thicken(renderer, page_url, response.text)
                pages[page_url] = html
                harvest.pages_read.append(page_url)
                harvest.images = (harvest.images + _images(html, page_url))[:16]
                harvest.socials = {**_socials(html), **harvest.socials}

    # Hand the readable text to Claude — menus are laid out too many ways to
    # parse structurally, but they're trivial to read.
    corpus = "\n\n".join(
        f"=== {url} ===\n" + visible_text(html)[:PAGE_TEXT_CHARS]
        for url, html in pages.items()
    )[:MAX_TEXT_CHARS]

    claude = claude or Claude.tracked("harvest")
    try:
        # The schema is the contract: a malformed reply raises here rather
        # than arriving as a shop that appears to have no menu.
        data = await claude.extract_model(
            f"Pages from a small business's website:\n\n{corpus}",
            Extracted,
            model=Model.HAIKU,
            system=EXTRACT_SYSTEM,
        )
    except Exception as e:
        harvest.error = f"extraction failed: {str(e)[:150]}"
        return harvest

    harvest.menu = [i for i in data.menu if i.name]

    # A menu that is a PDF or a photograph is invisible to everything above:
    # the crawler will not follow it because it is not a page. Read only when
    # the pages themselves yielded none — a site that lists its menu in HTML
    # and also links a printable copy should not be read twice, and the HTML
    # is the better source.
    if not harvest.menu:
        from loom.services import menu_doc

        for document in menu_doc.find(pages.get(base, ""), base)[:1]:
            harvest.menu = await menu_doc.read(document, claude=claude)

    harvest.hours = data.hours
    harvest.address = data.address
    harvest.phone = data.phone
    harvest.about = data.about

    # Ranked once, here, rather than per build: which photograph is the best
    # one is a fact about the photographs, and three art directions built from
    # the same harvest would otherwise pay to answer it three times. Fails open
    # by contract — the crawl order it replaces is a working order.
    from loom.services.image_pick import rank

    harvest.images = await rank(harvest.images, business=business, claude=claude)
    return harvest


async def harvest_lead(lead: dict, *, claude: Claude | None = None) -> Harvest:
    """Harvest for one saved lead, or explain why it can't be done.

    A shop with no website has nothing to read — the social handle picked up
    during scouting is the only lead, and that's a manual job.
    """
    url = lead.get("site_url")
    if not url:
        return Harvest(
            error="No website to read — check their Instagram by hand for a menu."
        )
    return await harvest_site(
        url,
        business=lead.get("google_name") or lead.get("site_title") or "",
        claude=claude,
    )


async def harvest_many(leads: list[dict], concurrency: int = 3) -> list[Harvest]:
    gate = asyncio.Semaphore(concurrency)
    claude = Claude.tracked("harvest")

    async def one(lead: dict) -> Harvest:
        async with gate:
            return await harvest_lead(lead, claude=claude)

    return list(await asyncio.gather(*(one(item) for item in leads)))


def as_dict(harvest: Harvest) -> dict[str, Any]:
    return harvest.model_dump(mode="json")
