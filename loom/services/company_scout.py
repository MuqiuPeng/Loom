"""Find companies worth contacting, without warehousing Google's data.

The split this module exists to enforce:

    Google Places  →  discovery only. Names, addresses, phones and websites
                      are Maps Platform Content; ToS 3.2.3 allows storing the
                      place_id indefinitely and essentially nothing else.
    Their website  →  yours to keep. Anything you read from a company's own
                      site — title, careers page, published contact address —
                      is not Google Content and carries no such restriction.

So Candidate keeps both, clearly separated, and `persistable()` returns only
the half you may store. Write that to Notion or Postgres; let the rest expire
with the process.

Two use cases, and they are legally different:

  * job outreach — a message asking about employment is not a commercial
    electronic message, so the Spam Act's consent rules don't bite.
  * freelance pitching — that IS commercial: you need consent (for a
    published business address, usually inferred), sender identification and
    a working opt-out. Keep the two campaigns, and their templates, apart.
    https://www.acma.gov.au/avoid-sending-spam
"""

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from html import unescape
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel, Field, computed_field

from loom.services import consent
from loom.services.broken_links import check_links
from loom.services.google.places import Place
from loom.services.places import PlaceResult
from loom.services.places import search as places_search
from loom.services.site_audit import (
    Finding,
    SiteAudit,
    audit_failure,
    audit_response,
    no_website_audit,
    refuses_unsolicited,
)

logger = logging.getLogger(__name__)

USER_AGENT = "loom-company-scout/0.1 (+contact via site owner)"
FETCH_TIMEOUT = 8.0
MAX_CONCURRENT_SITES = 5
MAX_PAGE_BYTES = 400_000
# Below this top-finding weight we have nothing worth emailing about yet,
# which is exactly when a dead link is worth going to look for. Matches
# min_problem_weight in config/email_templates.json — the threshold the
# first-contact template refuses to draft under.
LINK_CHECK_BELOW = 3

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MAILTO_RE = re.compile(r"mailto:([^\"'?>\s]+)", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_LINK_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
# Elements whose contents are code or markup, never page copy.
_NON_CONTENT_RE = re.compile(
    r"<(script|style|noscript|svg|template|head)\b[^>]*>.*?</\1\s*>|<!--.*?-->",
    re.I | re.S,
)
_WHITESPACE_RE = re.compile(r"\s+")

_CAREERS_RE = re.compile(
    r"career|jobs?\b|join[-_ ]?us|work[-_ ]?with[-_ ]?us|hiring|vacanc|employment|招聘|加入我们",
    re.I,
)

# A certificate failure does NOT arrive as an httpx.HTTPError. httpx lets
# ssl.SSLCertVerificationError through untouched, and that subclasses OSError,
# so `except httpx.HTTPError` misses it entirely — which meant the whole
# `certificate` branch of _classify below was unreachable, and a site with an
# expired cert crashed enrich() instead of being audited. Those sites are the
# best leads there are: "the browser blocks your site with a security warning"
# is the strongest opening line the pipeline can produce.
_TRANSPORT_ERRORS = (httpx.HTTPError, OSError)


def _classify(exc: Exception) -> str:
    """Map a transport failure to the reason a shop owner would recognise."""
    text = str(exc).lower()
    if "certificate" in text or "ssl" in text or "tlsv" in text:
        return "ssl"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "name or service not known" in text or "nodename nor servname" in text:
        return "dns"
    if "getaddrinfo" in text or "name resolution" in text:
        return "dns"
    return "unreachable"


# Addresses that appear on sites but are never a real contact. The
# placeholder domains are the ones template themes ship with — a real run on
# Marrickville cafes surfaced user@domain.com as a "contact address".
_EMAIL_NOISE = re.compile(
    # mystore.com is what Square ships in its own template, and it survived
    # every filter here: a real domain, a plausible local part, and the role
    # check reads "hi@" as general enquiries and calls it sendable. It reached
    # the send path on a live lead. Any store-shaped placeholder belongs with
    # the yourdomain family, not one domain past it.
    r"@(example|sentry|wixpress|godaddy|schema\.org|domain\.com|yourdomain|"
    r"yoursite|yourcompany|mydomain|email\.com|sentry\.io|"
    r"mystore|mysite|yourstore|yourbusiness|storename)"
    r"|^(you|your|youremail|your-email|user|username|name|email|info)@"
    r"(domain|example|yourdomain|yoursite|company)\."
    r"|\.(png|jpg|jpeg|gif|svg|webp)$",
    re.I,
)


class Candidate(BaseModel):
    """One company, with its Google-sourced and self-sourced halves separated."""

    # ── from the map provider — transient, do not persist ─────────────
    # Which provider found it. The same café has a different id in Google and
    # in Amap, so the pair (provider, place_id) is what identifies a business,
    # and the retention rules that apply to the fields below are the
    # provider's — see loom.services.places.base.RetentionPolicy.
    provider: str = "google"
    place_id: str = ""
    google_name: str = ""
    google_address: str = ""
    google_website: str | None = None
    google_phone: str | None = None
    primary_type: str | None = None
    google_rating: float | None = None
    google_rating_count: int | None = None
    google_price_level: str | None = None
    google_hours: list[str] = Field(default_factory=list)
    google_maps_uri: str | None = None
    google_types: list[str] = Field(default_factory=list)

    # ── from the company's own website — yours to keep ────────────────
    site_url: str | None = None  # final URL after our own fetch
    site_title: str | None = None
    careers_url: str | None = None
    emails: list[str] = Field(default_factory=list)
    audit: SiteAudit | None = None
    # Their page asked not to receive unsolicited commercial mail. Kept as a
    # field rather than only clearing the addresses so the reason survives:
    # an empty `emails` otherwise looks like "we found none".
    no_unsolicited: bool = False
    # {address: {url, how, at, refuses_unsolicited}} — the evidence that this
    # address was conspicuously published, which is the whole basis for
    # writing to it.
    email_sources: dict[str, dict] = Field(default_factory=dict)
    fetch_error: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_website(self) -> bool:
        return bool(self.google_website)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def opportunity(self) -> int:
        """How much is wrong with their web presence. Higher = more to fix."""
        return self.audit.score if self.audit else 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def signal(self) -> int:
        """How likely this business is to actually buy, 0-100.

        A separate axis from `opportunity` on purpose. A dead website says
        there is work to do; it says nothing about whether anyone will pay for
        it. The shop with the worst site in the suburb is often the one that
        stopped caring years ago, while a busy, well-reviewed operator with a
        merely dated site is the one who replies.

        Judged on what Places already gives us:
          reachable   an address to write to at all
          busy        review count — a going concern, not a hobby
          proud       rating — an owner who minds what people think
          budget      price level
        """
        score = 0
        if self.emails:
            score += 30          # can be approached in writing
        elif self.google_phone:
            score += 10          # phone only: possible, but a harder sell
        count = self.google_rating_count or 0
        if count >= 500:
            score += 25
        elif count >= 150:
            score += 18
        elif count >= 40:
            score += 10
        rating = self.google_rating or 0
        if rating >= 4.5:
            score += 25
        elif rating >= 4.0:
            score += 15
        elif rating > 0:
            score += 5
        level = (self.google_price_level or "").upper()
        if "EXPENSIVE" in level:
            score += 20
        elif "MODERATE" in level:
            score += 12
        elif "INEXPENSIVE" in level:
            score += 4
        if (self.audit and not self.audit.reachable) and not self.emails:
            # No site and no address: the only route left is walking in.
            score -= 15
        return max(0, min(100, score))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def priority(self) -> int:
        """Worth-doing-first: real work to do AND someone likely to pay.

        Multiplied rather than summed — a lead scoring zero on either axis is
        not half a lead, it is not a lead.
        """
        return round(self.opportunity * self.signal / 10)

    def persistable(self) -> dict:
        """The subset you may store long-term.

        place_id is exempt from the caching restriction and is what lets you
        re-query Google later instead of keeping a stale copy of its data.
        The audit is derived from their page, so it's self-sourced too.
        """
        return {
            "provider": self.provider,
            "place_id": self.place_id,
            "site_url": self.site_url,
            "site_title": self.site_title,
            "careers_url": self.careers_url,
            "emails": self.emails,
            # Must persist: the refusal is on their page today and may not be
            # tomorrow, and a lead that comes back through a later scan with a
            # forgotten flag is a lead we write to anyway.
            "no_unsolicited": self.no_unsolicited,
            "email_sources": self.email_sources,
            "audit": self.audit.model_dump(mode="json") if self.audit else None,
            "signal": self.signal,
            "checked_at": self.checked_at.isoformat(),
        }


# ── website enrichment ───────────────────────────────────────────────


def _text(html: str) -> str:
    """Tags out, entities decoded, whitespace collapsed.

    Decoding is not cosmetic here. The <title> of a Shopify page routinely
    contains &ndash; and &amp;, and this feeds site_title, which the panel
    shows and which the email templates fall back to when Google has no name
    for the business. A shop addressed as "Dulwich Hill &ndash; Cafe Calibre"
    in the first line of a cold email is a worse mistake than any of the
    layout problems the email is written to point out.
    """
    return _WHITESPACE_RE.sub(" ", unescape(_TAG_RE.sub(" ", html))).strip()


def visible_text(html: str) -> str:
    """The text a human actually sees on the page.

    Stripping tags alone is not enough: a modern theme carries far more
    JavaScript than prose, so `_text` on a Shopify page returns ~79k
    characters of `window.THEME = {...}`. Anything reading a page for meaning
    — menu extraction, contact addresses — must drop script, style and markup
    payloads first, or it is reading the theme rather than the business.
    """
    cleaned = _NON_CONTENT_RE.sub(" ", html)
    return _WHITESPACE_RE.sub(" ", unescape(_TAG_RE.sub(" ", cleaned))).strip()


def _note_sources(
    candidate: "Candidate", found: list[str], url: str | None, how: str
) -> None:
    """Record where an address was published, at the moment it was read.

    The Spam Act infers consent from conspicuous publication, but only under
    conditions that describe the page as it stood: was the address plainly
    published, does it look agreed to, was there a statement refusing
    unsolicited commercial mail. Section 16(5) puts the burden of proving that
    on the sender, and a bare string in an `emails` list proves nothing.

    Captured here rather than reconstructed later, because "what did that page
    say in August" stops being answerable the moment the page changes.

    First sighting wins: a mailto link on the contact page is better evidence
    than the same address appearing again in a footer.
    """
    if not url:
        return
    for raw in found:
        address = raw.strip().lower()
        if not address or address in candidate.email_sources:
            continue
        # The role verdict is stored with the sighting rather than computed
        # at send time, because it is part of the same contemporaneous record:
        # "this is where I saw it, this is what the address is for, this is
        # why a website offer is relevant to that."
        verdict = consent.classify(address)
        candidate.email_sources[address] = {
            "url": url,
            "how": how,
            "at": datetime.now(UTC).isoformat(),
            "role": verdict["role"],
            "tier": verdict["tier"],
            "relevance": verdict["reason"],
            # Recorded per address as it stood, not only as a lead-level flag:
            # the question is always about a particular page at a particular
            # time.
            "refuses_unsolicited": candidate.no_unsolicited,
        }


def _clean_emails(found: list[str]) -> list[str]:
    """Normalise, drop template placeholders, and collapse truncations.

    Real pages produce escaped fragments (`hello@shop.com\\,` out of embedded
    JSON) and truncated twins (`hello@shop.com` alongside the real
    `hello@shop.com.au`). Both look like distinct addresses to a plain dedupe.
    """
    seen: list[str] = []
    for raw in found:
        # Cut at the first escape or quote — everything after is markup.
        email = re.split(r"[\\\"'<>]", raw.strip())[0]
        email = email.strip().strip(".,;:").lower()
        if not email or _EMAIL_NOISE.search(email) or email in seen:
            continue
        seen.append(email)

    # Drop any address that is a strict prefix of another at a domain
    # boundary — "shop.com" is a truncation of "shop.com.au", not a second inbox.
    return [
        e
        for e in seen
        if not any(other != e and other.startswith(e + ".") for other in seen)
    ]


def _find_careers_link(html: str, base: str) -> str | None:
    for href, label in _LINK_RE.findall(html):
        if _CAREERS_RE.search(href) or _CAREERS_RE.search(_text(label)):
            joined = urljoin(base, href)
            if joined.startswith(("http://", "https://")):
                return joined
    return None


class _SiteFetcher:
    """Polite one-or-two page fetch of a company's own site."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self._robots: dict[str, RobotFileParser | None] = {}

    async def _allowed(self, url: str) -> bool:
        """Honour robots.txt. A missing or unreadable file means allowed."""
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = None
            try:
                response = await self.client.get(f"{origin}/robots.txt")
                if response.status_code < 400:
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
            except _TRANSPORT_ERRORS:
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    async def _get(self, url: str) -> tuple[httpx.Response | None, int]:
        """Fetch a page, timing ONLY the page itself.

        The robots.txt round trip must stay outside the measurement — folding
        it in inflated every first-hit-per-host by a full request and pushed
        healthy sites over the slow threshold.
        """
        if not await self._allowed(url):
            return None, 0
        started = time.perf_counter()
        response = await self.client.get(url)
        return response, int((time.perf_counter() - started) * 1000)

    async def _add_link_findings(
        self, candidate: Candidate, final_url: str, html: str
    ) -> None:
        """Look for dead links, but only on sites that still need a reason.

        This is the one check that costs real outbound traffic — up to a few
        dozen probes against a stranger's server, multiplied by the five sites
        enriched at once. Spending that on every candidate would be both slow
        and rude.

        It buys nothing on a site that has already failed loudly. A page with
        no HTTPS, no viewport and a 2016 copyright hands us an opening line
        for free; finding a dead link there changes no decision and writes no
        email. The businesses worth the requests are the ones whose sites look
        broadly fine — those are the leads with nothing to say about them yet,
        and a dead booking link is exactly the concrete thing that turns a
        polite non-approach into a real one.

        So the gate is the weight of what we already have, not the number of
        findings: the first-contact template refuses to draft on anything
        under weight 3, and a page scoring 1 + 1 + 1 is still nothing to write
        about.
        """
        audit = candidate.audit
        if not audit or not audit.reachable:
            return
        if audit.findings and max(f.weight for f in audit.findings) >= LINK_CHECK_BELOW:
            return
        try:
            # Our own client, not the module's default one: it carries the
            # scout's user agent and timeouts, and it is what the offline
            # check suite stubs. A check that quietly opened its own
            # connection would make that suite hit real servers.
            audit.findings.extend(
                await check_links({final_url: html}, client=self.client)
            )
        except Exception as e:
            # Never let a supporting check take down the enrichment that found
            # the lead in the first place.
            candidate.fetch_error = candidate.fetch_error or f"link check: {e}"[:200]

    async def _favicon_ok(self, site_url: str) -> bool | None:
        """Whether /favicon.ico is actually there.

        Worth the extra request because the markup cannot answer it: a site
        with no <link rel="icon"> usually still has a favicon at the default
        path, and telling an owner their tab is blank when it isn't is the
        kind of error that ends the conversation in the first line.

        Returns None on any doubt, which switches the check off rather than
        guessing.
        """
        parts = urlparse(site_url)
        if not parts.scheme or not parts.hostname:
            return None
        target = f"{parts.scheme}://{parts.netloc}/favicon.ico"
        try:
            response = await self.client.head(target, follow_redirects=True)
        except _TRANSPORT_ERRORS:
            return None
        if response.status_code >= 400:
            return False
        # Some hosts answer everything with 200 and an HTML error page.
        kind = response.headers.get("content-type", "").lower()
        if kind.startswith("text/html"):
            return False
        return True

    async def enrich(self, candidate: Candidate) -> Candidate:
        url = candidate.google_website
        if not url:
            # No site listed at all — that IS the finding.
            candidate.audit = no_website_audit()
            return candidate

        try:
            home, load_ms = await self._get(url)
        except _TRANSPORT_ERRORS as e:
            candidate.fetch_error = str(e)[:200]
            candidate.audit = audit_failure(url, _classify(e), str(e)[:120])
            return candidate

        if home is None:
            # robots.txt said no. We can't judge a page we won't read.
            candidate.fetch_error = "blocked by robots.txt"
            return candidate

        html = home.text[:MAX_PAGE_BYTES]
        candidate.site_url = str(home.url)
        candidate.audit = audit_response(
            url,
            final_url=str(home.url),
            status_code=home.status_code,
            load_ms=load_ms,
            html=html,
            # The Places phone is the half of the comparison the page can't
            # supply. Nothing is stored from it — it is read, compared, and
            # only the verdict survives.
            google_phone=candidate.google_phone,
            favicon_ok=await self._favicon_ok(str(home.url)),
        )

        # A legal gate, checked before anything else is done with the page.
        # Inferred consent is the only basis this pipeline has for writing to
        # a published business address, and a page that refuses unsolicited
        # commercial mail removes it. Clearing the addresses is what actually
        # enforces it — a flag nobody reads would not.
        if refuses_unsolicited(html):
            candidate.no_unsolicited = True
            candidate.emails = []

        await self._add_link_findings(candidate, str(home.url), html)

        if home.status_code >= 400:
            return candidate

        title = _TITLE_RE.search(html)
        if title:
            candidate.site_title = _text(title.group(1)).strip()[:200]

        emails = _MAILTO_RE.findall(html) + _EMAIL_RE.findall(_text(html))
        _note_sources(candidate, _MAILTO_RE.findall(html), str(home.url), "mailto link")
        _note_sources(candidate, _EMAIL_RE.findall(_text(html)), str(home.url), "page text")
        candidate.careers_url = _find_careers_link(html, str(home.url))

        # One level deeper, only for the careers page — that's where a
        # jobs@ address usually lives.
        if candidate.careers_url:
            try:
                careers, _ = await self._get(candidate.careers_url)
            except _TRANSPORT_ERRORS:
                careers = None
            if careers is not None and careers.status_code < 400:
                page = careers.text[:MAX_PAGE_BYTES]
                emails += _MAILTO_RE.findall(page) + _EMAIL_RE.findall(_text(page))
                _note_sources(candidate, _MAILTO_RE.findall(page),
                              candidate.careers_url, "mailto link")
                _note_sources(candidate, _EMAIL_RE.findall(_text(page)),
                              candidate.careers_url, "page text")

        candidate.emails = _clean_emails(emails)
        # Keep provenance only for addresses that survived cleaning, so the
        # record does not accumulate entries for template placeholders and
        # image filenames that were never going to be written to.
        kept = set(candidate.emails)
        candidate.email_sources = {
            address: detail
            for address, detail in candidate.email_sources.items()
            if address in kept
        }
        return candidate


# ── orchestration ────────────────────────────────────────────────────


def _to_candidate(p: PlaceResult) -> "Candidate":
    return Candidate(
        place_id=p.provider_place_id,
        provider=p.provider,
        google_name=p.name,
        google_address=p.address,
        google_website=p.website,
        google_phone=p.phone,
        primary_type=p.primary_type,
        google_rating=p.rating,
        google_rating_count=p.rating_count,
        google_price_level=p.price_level,
        google_hours=p.hours,
        google_maps_uri=p.map_uri,
        google_types=p.types,
    )


def _in_country(candidate: "Candidate", country: str | None) -> bool:
    """Whether this result is in the country that was searched.

    locationRestriction handles a search that names an area, and this handles
    the one that does not — a query with no `near` has no geographic parameter
    at all, so nothing but the words stops it landing anywhere on earth.

    It is worth two guards rather than one because of what the pipeline
    downstream assumes. The consent argument is written against the Australian
    Spam Act, the quote is in Australian dollars, the follow-up waits for
    business hours in Sydney and the signature carries an Australian business
    name. A shop in Mesa, Arizona reaching the end of that is not a lead with
    the wrong postcode; it is the wrong law, the wrong currency and a message
    that arrives in the middle of their night.

    Unknown country, or an address that names none, passes: this drops what is
    demonstrably foreign, not everything it cannot place.
    """
    if not country:
        return True
    from loom.services.area_survey import areas_config

    countries = areas_config().get("countries") or {}
    expected = (countries.get(country.upper()) or {}).get("name")
    if not expected:
        return True
    address = (candidate.google_address or "").strip()
    # Google writes the country after the last comma and spells it out, so an
    # address with no comma carries no country and is not evidence of anything.
    # An exact match on that field rather than a substring test — otherwise a
    # search for New Zealand keeps anything ending in "Zealand".
    if "," not in address:
        return True
    tail = address.rsplit(",", 1)[-1].strip().lower()
    if tail in ("", expected.lower()):
        return True
    logger.info(
        "dropping %s — %s is not in %s", candidate.google_name, tail, expected
    )
    return False


async def discover(
    queries: list[str],
    *,
    near: str | None = None,
    radius_m: int = 5000,
    max_results: int = 20,
    country: str | None = None,
    provider: str | None = None,
) -> list[Candidate]:
    """Run every query against the map provider and merge the results.

    Merged on (provider, place_id): providers match on their own category
    vocabulary, so "plumber" and "plumbing service" overlap heavily, and a
    business that answers to both must not be enriched — or emailed — twice.
    """
    if not queries:
        return []

    async def one(term: str) -> list[Candidate]:
        found = await places_search(
            term,
            near=near,
            radius_m=radius_m,
            max_results=max_results,
            country=country,
            provider_name=provider,
        )
        return [_to_candidate(p) for p in found]

    batches = await asyncio.gather(*(one(q) for q in queries))

    merged: dict[tuple[str, str], Candidate] = {}
    for batch in batches:
        for candidate in batch:
            if not _in_country(candidate, country):
                continue
            merged.setdefault((candidate.provider, candidate.place_id), candidate)
    return list(merged.values())


async def enrich_candidates(
    candidates: list[Candidate], *, render: bool = True
) -> list[Candidate]:
    """Read each company's own site: title, careers page, emails, audit."""
    if not candidates:
        return []

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        fetcher = _SiteFetcher(client)
        gate = asyncio.Semaphore(MAX_CONCURRENT_SITES)

        async def one(candidate: Candidate) -> Candidate:
            async with gate:
                return await fetcher.enrich(candidate)

        candidates = list(await asyncio.gather(*(one(c) for c in candidates)))

    if render:
        await _render_audit(candidates)
    return candidates


async def refresh_contacts(lead: dict) -> dict:
    """Read a stored lead's site again for addresses and where they were found.

    Provenance is written once, at first sighting, during the scout — and
    nothing downstream ever touches `emails` again. So a lead scouted before
    that code existed has no record and had no way to acquire one, which was
    survivable only while a missing record counted as no objection. It counts
    as no evidence now, and this is the way back.

    Only the contact fields come out. `enrich` also produces an audit, and
    returning it would let a harvest quietly rewrite findings somebody was
    reading — re-auditing is its own stage, with its own button.
    """
    url = (lead.get("site_url") or lead.get("google_website") or "").strip()
    if not url:
        return {}

    candidate = Candidate(
        provider=lead.get("provider") or "google",
        place_id=lead.get("place_id") or "",
        google_name=lead.get("google_name") or "",
        google_website=url,
        google_phone=lead.get("google_phone"),
    )
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        candidate = await _SiteFetcher(client).enrich(candidate)

    return {
        "emails": candidate.emails,
        "email_sources": candidate.email_sources,
        "no_unsolicited": candidate.no_unsolicited,
    }


async def scout(
    query: str | list[str],
    *,
    near: str | None = None,
    radius_m: int = 5000,
    max_results: int = 20,
    enrich: bool = True,
    render: bool = True,
    country: str | None = None,
    provider: str | None = None,
) -> list[Candidate]:
    """Discover companies, then read what matters from their own sites.

    `query` may be one term or several — several are merged before any site is
    fetched, so overlapping industry queries cost one crawl per business
    rather than one per query that matched it.

    `country` picks the map provider — see loom.services.places. Left off, the
    unrestricted fallback answers, which is Google.
    """
    queries = [query] if isinstance(query, str) else list(query)
    candidates = await discover(
        queries,
        near=near,
        radius_m=radius_m,
        max_results=max_results,
        country=country,
        provider=provider,
    )

    if enrich:
        candidates = await enrich_candidates(candidates, render=render)

    await _log_run(", ".join(queries), near, candidates)
    return candidates


async def _render_audit(candidates: list[Candidate]) -> None:
    """Add what a phone actually sees to each audit.

    The static rules can only read the HTML, and the defect that sells this
    work hardest — a site that is fine on a desktop and broken on a phone —
    leaves no trace there. A Wix page carries a correct viewport tag and still
    blows out sideways.
    """
    from loom.services.render_check import render_audit

    live = [c for c in candidates if c.site_url and c.audit and c.audit.reachable]
    if not live:
        return

    found = await render_audit([c.site_url for c in live if c.site_url])
    for candidate in live:
        for problem in found.get(candidate.site_url or "", []):
            # Rendered evidence supersedes the static guess at the same fault.
            if problem["code"] == "mobile_broken" and candidate.audit:
                candidate.audit.findings = [
                    f for f in candidate.audit.findings
                    if f.code != "not_mobile_ready"
                ]
            if candidate.audit:
                candidate.audit.findings.append(Finding(**problem))


def summarise(found: list[Place] | list[Candidate]) -> dict:
    """Aggregate counts only — the shape to keep when you must not keep detail.

    This is the ToS-clean way to answer "is there a market here?": run it,
    record the numbers, throw the list away.
    """
    total = len(found)
    with_site = sum(1 for f in found if f.has_website)
    by_type: dict[str, int] = {}
    by_finding: dict[str, int] = {}
    for item in found:
        key = item.primary_type or "unknown"
        by_type[key] = by_type.get(key, 0) + 1
        audit = getattr(item, "audit", None)
        for code in audit.codes if audit else ():
            by_finding[code] = by_finding.get(code, 0) + 1
    return {
        "total": total,
        "with_website": with_site,
        "without_website": total - with_site,
        "pct_without_website": round(100 * (total - with_site) / total, 1) if total else 0.0,
        "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "by_finding": dict(sorted(by_finding.items(), key=lambda kv: -kv[1])),
    }


async def _log_run(query: str, near: str | None, candidates: list[Candidate]) -> None:
    try:
        from loom.services.logger import logger as loom_logger

        await loom_logger.info(
            "user_action",
            "company_scout.run",
            f"scouted {len(candidates)} companies for {query!r}",
            service="company_scout",
            query=query,
            near=near,
            found=len(candidates),
            with_website=sum(1 for c in candidates if c.has_website),
            with_email=sum(1 for c in candidates if c.emails),
        )
    except Exception as e:  # pragma: no cover - defensive
        print(f"[LOG_ERROR] company_scout: {e}")
