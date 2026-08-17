"""Find links a customer would click that don't go anywhere.

The rest of site_audit.py judges a page by reading it. This is the one check
that has to leave the building: a dead link looks identical to a live one in
the HTML, and the only way to know "the link to your menu is dead" is to
knock on the door.

That makes it the most persuasive finding we produce and the most dangerous.
The approach email leads on it, so a false positive doesn't cost us a weak
sentence — it tells a shop owner their site is broken when it isn't, in
writing, from a stranger. Everything below is bent toward the same rule:

    when in doubt, report nothing.

Silence costs one lead. A wrong accusation costs the pitch.

Where the HTML comes from
-------------------------
Nothing in the codebase keeps the pages it fetches:

  * company_scout._SiteFetcher.enrich() holds `html = home.text[:MAX_PAGE_BYTES]`
    as a local, hands it to audit_response(html=...), reads the title/emails/
    careers link out of it, and drops it. Candidate has no HTML field.
  * site_harvest.harvest_site() builds `pages = {url: response.text}` for up
    to MAX_PAGES pages, feeds visible_text() of them to Claude, and drops
    that too. Harvest keeps `pages_read` — URLs only.

So the raw HTML is discarded in both paths, and it is currently fetched
twice per business (once by the scout, once by the harvest). This check
therefore takes the HTML as an argument, exactly the way audit_response does,
and must be called from inside the scope where that local is still alive. It
never crawls. Given `pages`, its only network traffic is the link probes
themselves.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx

from loom.services.site_audit import Finding

# Deliberately a local copy rather than an import from company_scout: that
# module imports this one, and pulling a constant back the other way would
# close the loop. Keep the two in step by hand — it is one string, and a
# cycle here would break the whole scout path at import time.
USER_AGENT = "loom-company-scout/0.1 (+contact via site owner)"


# ── budget ───────────────────────────────────────────────────────────
#
# This runs against a stranger's server, uninvited, and the business owner
# has never heard of us. The numbers below are chosen so that our traffic is
# quieter than one person browsing the site in a browser — if a sysadmin ever
# looks at the access log, the honest answer has to be "that's one visitor".
#
# Chrome opens 6 concurrent connections per origin and a single page load
# fires 30-80 requests. At 3 concurrent and ~50 requests total we sit visibly
# under that, with no burst, and finish in seconds. There is no upside to
# going faster: the whole check is one item in a batch that is already gated
# at MAX_CONCURRENT_SITES=5 in company_scout, so raising this multiplies
# against that gate and is how a polite scout turns into a small DDoS.

MAX_PER_HOST = 3        # concurrent requests to any one origin — half a browser
MAX_CONCURRENT = 8      # across all hosts; caps the multiplier when batching
LINK_TIMEOUT = 6.0      # per request; a slow link is not a broken link
TOTAL_BUDGET = 25.0     # wall clock for the whole check, partial results kept
CONFIRM_DELAY = 1.2     # pause before re-testing a 5xx, so a blip isn't a verdict

# How many links we are willing to touch. Selection is by value, not by
# document order, so the cap spends the budget on the links that carry the
# pitch (menu, order, book) rather than on the fifteenth footer link.
MAX_INTERNAL = 40
MAX_EXTERNAL = 12
MAX_EXTERNAL_PER_HOST = 2

# The kill switch. If half of everything we touched failed, the failure is
# ours or a WAF's, not the site's — see _too_noisy().
NOISE_FLOOR = 0.5
MIN_CHECKED = 4

MAX_LABEL_CHARS = 40


# ── what to look at ──────────────────────────────────────────────────

# Same shape as company_scout._LINK_RE. The codebase has no bs4 dependency
# and parses links with a regex everywhere; adding a parser for one check
# would be a new dependency for no new capability.
_LINK_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# mailto:, tel:, javascript:, sms:, #anchor — a browser never issues a request
# for these, so there is nothing to test. A malformed mailto is a real defect
# but it is a syntax check, not a link check, and mixing them here would put
# an unverifiable claim in the same finding as a verifiable one.
_HTTP_SCHEMES = ("http://", "https://")

# Links whose anchor text or path says a customer is trying to buy something.
# \b throughout on purpose: "facebook" contains "book" and "border" contains
# "order", and both would otherwise promote a footer link to a headline.
_VALUABLE_RE = re.compile(
    r"\bmenus?\b|\border\b|\bbook(?:ing)?\b|\breserv|\bcontact\b|\bshop\b|"
    r"\bstore\b|\bbuy\b|\bgift\b|\bcater|\bdeliver|\bprices?\b|\bhours?\b|"
    r"\bfind[-_ ]?us\b|\blocations?\b|\bappointment",
    re.I,
)

# Paths that are plumbing, not pages a customer navigates to. A 403 on
# /wp-admin is correct behaviour, and reporting it as a broken link would be
# both wrong and embarrassing.
_SKIP_PATH_RE = re.compile(
    r"/wp-(admin|login|json)|/xmlrpc\.php|/logout|/signout|/sign-out|"
    r"/my-?account|/customer/account|/admin\b|/feed/?$|\?add-to-cart=|"
    r"/cdn-cgi/|/\?(?:s|q|search)=",
    re.I,
)

# Hosts that answer a bot with 403 or a login wall no matter what. They are
# the single largest source of false "dead link" verdicts on small business
# sites, because every one of these sites links to Instagram. We cannot tell
# their bot wall from a deleted page, so we don't guess.
_BOT_WALLED = (
    "instagram.com",
    "facebook.com",
    "fb.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "pinterest.com",
    "doordash.com",
    "ubereats.com",
    "menulog.com.au",
    "deliveroo.com",
    "opentable.com",
    "yelp.com",
    "tripadvisor.com",
    "google.com",       # maps links redirect through consent interstitials
    "goo.gl",
    "maps.app.goo.gl",
)


@dataclass
class Link:
    """One href worth testing, with why we think it's worth testing."""

    url: str            # normalised, absolute
    label: str          # anchor text as a customer sees it
    internal: bool
    value: int          # 3 = money link, 2 = internal, 1 = external

    @property
    def host(self) -> str:
        return (urlparse(self.url).hostname or "").lower()


@dataclass
class LinkStatus:
    """The verdict on one link, and the evidence for it."""

    url: str
    verdict: str        # ok | gone | dead_host | server_error | cert | blocked | unknown
    status_code: int | None = None
    note: str = ""
    requests: int = 0

    @property
    def broken(self) -> bool:
        return self.verdict in ("gone", "dead_host", "server_error", "cert")

    @property
    def conclusive(self) -> bool:
        """We learned something. `unknown` means we failed, not that they did."""
        return self.verdict != "unknown"


# ── extraction and selection (pure — no network) ─────────────────────


def _label_of(raw_html: str) -> str:
    """The words on the link, as a customer reads them."""
    text = _WHITESPACE_RE.sub(" ", unescape(_TAG_RE.sub(" ", raw_html))).strip()
    return text[:MAX_LABEL_CHARS]


def normalise(url: str) -> str:
    """Collapse the spellings of one destination into one key.

    Fragment goes (the server never sees it) and scheme/host are lowercased.
    Path case and query are left alone — /Menu and /menu are different files
    on any case-sensitive host, and assuming otherwise would merge a live
    page with a dead one and let us report either.
    """
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.port and not (
        (parts.scheme == "http" and parts.port == 80)
        or (parts.scheme == "https" and parts.port == 443)
    ):
        host = f"{host}:{parts.port}"
    return urlunparse(
        (parts.scheme.lower(), host, parts.path or "/", parts.params, parts.query, "")
    )


def extract_links(html: str, base: str) -> list[Link]:
    """Every testable link on one page, valued by how much a customer wants it."""
    origin = (urlparse(base).hostname or "").lower()
    found: list[Link] = []

    for href, raw_label in _LINK_RE.findall(html):
        href = unescape(href.strip())
        if not href or href.startswith("#"):
            continue
        url = urljoin(base, href)
        if not url.lower().startswith(_HTTP_SCHEMES):
            continue  # mailto:, tel:, javascript:, sms:, data: — nothing to request

        url = normalise(url)
        parts = urlparse(url)
        host = (parts.hostname or "").lower()
        if _SKIP_PATH_RE.search(parts.path + ("?" + parts.query if parts.query else "")):
            continue

        # www.shop.com and shop.com are the same business; a subdomain like
        # book.shop.com is theirs too and its being dead is still their problem.
        root = origin[4:] if origin.startswith("www.") else origin
        internal = bool(root) and (host == root or host.endswith("." + root))
        if not internal and any(
            host == h or host.endswith("." + h) for h in _BOT_WALLED
        ):
            continue

        label = _label_of(raw_label)
        valuable = bool(_VALUABLE_RE.search(f"{parts.path} {label}"))
        found.append(
            Link(
                url=url,
                label=label,
                internal=internal,
                value=3 if valuable else (2 if internal else 1),
            )
        )
    return found


def select_links(links: list[Link]) -> list[Link]:
    """Dedupe and bound.

    Deduplication is the whole reason this is cheap: nav and footer links
    repeat on every page of the crawl, so six harvested pages of forty links
    each collapse to well under a hundred distinct destinations, and the site's
    own menu link gets tested once rather than six times.

    External links are checked, not skipped, and that is a deliberate call.
    A dead link to the booking system or the old delivery partner is exactly
    as broken to the customer standing in the rain as an internal one, and
    it's the case the owner is least likely to have noticed — nobody re-tests
    a link they added in 2019. What we bound is the cost: at most two links
    per external host and MAX_EXTERNAL overall, so a site that links to the
    same aggregator thirty times can't eat the budget.
    """
    best: dict[str, Link] = {}
    for link in links:
        seen = best.get(link.url)
        if seen is None:
            best[link.url] = link
            continue
        # Keep the most valuable framing of a repeated href: the same URL is
        # often a bare logo link with no text in one place and "View our menu"
        # in another, and the words are what ends up in the email.
        if link.value > seen.value or (
            link.value == seen.value and link.label and not seen.label
        ):
            best[link.url] = link

    internal = sorted(
        (link for link in best.values() if link.internal),
        key=lambda link: (-link.value, link.url),
    )[:MAX_INTERNAL]

    external: list[Link] = []
    per_host: dict[str, int] = {}
    for link in sorted(
        (link for link in best.values() if not link.internal),
        key=lambda link: (-link.value, link.url),
    ):
        if per_host.get(link.host, 0) >= MAX_EXTERNAL_PER_HOST:
            continue
        per_host[link.host] = per_host.get(link.host, 0) + 1
        external.append(link)
        if len(external) >= MAX_EXTERNAL:
            break

    return internal + external


# ── the probe ────────────────────────────────────────────────────────
#
# HEAD or GET
# -----------
# HEAD first, because it's free — no body crosses the wire and a healthy site
# is almost entirely healthy links. But a large minority of small-business
# hosts handle HEAD badly: cheap shared hosting and PHP front controllers
# answer 405 or 501, some WAFs treat a bodyless request as a bot signature and
# return 403, and a handful return 404 for HEAD on a page that GETs 200.
#
# So the rule is asymmetric, and that asymmetry is the point:
#
#     a 2xx/3xx HEAD is trusted and ends the check;
#     ANY other HEAD result is discarded and re-tested with GET.
#
# A HEAD is never allowed to convict. In the common case that costs one cheap
# request per link; in the failure case it removes the entire class of
# "this host doesn't do HEAD" false positives. The GET is streamed and the
# body is never read, so we pay for headers, not for a PDF menu.

_STATUS_BLOCKED = {401, 403, 407, 429, 451}   # a wall, not a hole
_STATUS_GONE = {404, 410}

# httpx does NOT reliably wrap TLS failures: an expired certificate surfaces
# as a raw ssl.SSLCertVerificationError straight out of client.stream, not as
# httpx.ConnectError. Catching only httpx.HTTPError let the one verdict we
# most wanted from a failed handshake — "cert" — escape as a crash instead.
# ssl.SSLError subclasses OSError, so this pair covers both spellings.
_TRANSPORT_ERRORS = (httpx.HTTPError, OSError)


def verdict_for_status(code: int) -> str:
    """Map a status a GET actually returned to what we're willing to claim.

    The judgement calls, and why:

      404 / 410   broken. The one unambiguous case, and the only one the
                  pitch really needs.
      5xx         broken only after a second try — see _probe(). A single 502
                  is as likely to be a deploy or a cold container as a fault.
      401/403/429 NOT broken. This is the important one. A 403 overwhelmingly
                  means we were identified as a bot, not that the page is
                  gone; Cloudflare, Wordfence and Sucuri all answer strangers
                  this way. Reporting these would put a wrong claim in nearly
                  every email we send to a site behind Cloudflare.
      3xx         not seen here — httpx follows redirects and we judge the
                  destination. A long redirect chain is untidy, not broken,
                  and the classic "redirects to the homepage instead of 404"
                  soft-404 is deliberately NOT chased: detecting it means
                  guessing whether a 200 page is really the page asked for,
                  and every heuristic for that is wrong often enough to
                  disqualify it from an email.
      other 4xx   unknown. 400/405/406/415 from a GET means we confused the
                  server, which is our problem to be quiet about.
    """
    if code in _STATUS_GONE:
        return "gone"
    if code in _STATUS_BLOCKED:
        return "blocked"
    if code >= 500:
        return "server_error"
    if code < 400:
        return "ok"
    return "unknown"


def _transport_verdict(exc: Exception) -> str:
    """Classify a failure that never reached a status line.

    Mirrors company_scout._classify, but the conclusions differ because the
    stakes do: there, the site itself failed to load and that IS the finding;
    here, a link failing while the homepage loaded fine is at least as likely
    to be us.

      DNS       broken. A hostname that doesn't resolve is the most reliable
                verdict available — it isn't a bot wall, a slow server or a
                bad path, it's a domain that no longer exists.
      TLS       broken. The visitor gets a full-page browser security warning,
                which is precisely the "show me" moment we want.
      timeout   NOT broken, ever. It could be their host, our network, or a
                6-second budget that was simply too short for a big PDF.
      connect   NOT broken. Same reasoning.
    """
    text = str(exc).lower()
    if "certificate" in text or "ssl" in text or "tlsv" in text or "hostname mismatch" in text:
        return "cert"
    if (
        "name or service not known" in text
        or "nodename nor servname" in text
        or "getaddrinfo" in text
        or "name resolution" in text
        or "no address associated" in text
    ):
        return "dead_host"
    return "unknown"


async def _status(client: httpx.AsyncClient, method: str, url: str) -> httpx.Response:
    """One request whose body we never read.

    Streaming and abandoning is how a GET stays as cheap as a HEAD: we get the
    status line and headers, then close. Downloading a 12MB PDF menu to learn
    that it exists would be rude and slow.
    """
    async with client.stream(
        method, url, timeout=LINK_TIMEOUT, follow_redirects=True
    ) as response:
        return response


async def _probe(client: httpx.AsyncClient, link: Link) -> LinkStatus:
    """Decide about one link, spending as few requests as the answer allows."""
    requests = 0
    try:
        response = await _status(client, "HEAD", link.url)
        requests += 1
        if response.status_code < 400:
            return LinkStatus(link.url, "ok", response.status_code, requests=requests)
        head_note = f"HEAD {response.status_code}"
    except _TRANSPORT_ERRORS as e:
        requests += 1
        head_note = f"HEAD failed: {type(e).__name__}"
        # Not conclusive on its own — plenty of hosts reset a HEAD outright.

    try:
        response = await _status(client, "GET", link.url)
        requests += 1
    except _TRANSPORT_ERRORS as e:
        requests += 1
        verdict = _transport_verdict(e)
        if verdict == "unknown":
            return LinkStatus(link.url, "unknown", note=str(e)[:120], requests=requests)
        # DNS and TLS failures are deterministic in theory and flaky in
        # practice (a resolver hiccup, a mid-rotation cert). One confirmation
        # is cheap insurance against putting a transient in an email.
        await asyncio.sleep(CONFIRM_DELAY)
        try:
            response = await _status(client, "GET", link.url)
            requests += 1
        except _TRANSPORT_ERRORS as again:
            requests += 1
            if _transport_verdict(again) == verdict:
                return LinkStatus(link.url, verdict, note=str(again)[:120], requests=requests)
            return LinkStatus(link.url, "unknown", note=str(again)[:120], requests=requests)
        return LinkStatus(link.url, "ok", response.status_code, requests=requests)

    verdict = verdict_for_status(response.status_code)
    if verdict == "server_error":
        await asyncio.sleep(CONFIRM_DELAY)
        try:
            second = await _status(client, "GET", link.url)
            requests += 1
        except _TRANSPORT_ERRORS:
            return LinkStatus(link.url, "unknown", response.status_code, requests=requests)
        if second.status_code < 500:
            # It recovered. That was a blip, and a blip is not a finding.
            return LinkStatus(
                link.url,
                verdict_for_status(second.status_code),
                second.status_code,
                requests=requests,
            )
        return LinkStatus(
            link.url, "server_error", second.status_code,
            note=f"{head_note}, twice", requests=requests,
        )

    return LinkStatus(link.url, verdict, response.status_code, note=head_note, requests=requests)


# ── robots ───────────────────────────────────────────────────────────


class _Robots:
    """robots.txt for the site's own origin only.

    Consistent with _SiteFetcher: a path we're asked not to touch is a path we
    can't judge, and skipping it can only remove findings. External hosts are
    deliberately not gated — fetching robots.txt per external host would
    roughly double the requests this check makes, which is worse for the very
    servers the politeness is meant to protect, and we make at most two
    requests to any of them.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self._parsers: dict[str, RobotFileParser | None] = {}

    async def allows(self, url: str) -> bool:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._parsers:
            parser: RobotFileParser | None = None
            try:
                response = await self.client.get(f"{origin}/robots.txt", timeout=LINK_TIMEOUT)
                if response.status_code < 400:
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
            except _TRANSPORT_ERRORS:
                parser = None
            self._parsers[origin] = parser
        parser = self._parsers[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)


# ── pooled client ────────────────────────────────────────────────────
#
# Same shape as loom.services.google.client: one client per process, created
# lazily behind a lock, closed explicitly on shutdown. Connection reuse is
# what keeps a 50-link check from opening 50 TLS handshakes against a small
# shared host.

_http_client: httpx.AsyncClient | None = None
_http_lock = asyncio.Lock()


async def _http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        async with _http_lock:
            if _http_client is None or _http_client.is_closed:
                _http_client = httpx.AsyncClient(
                    timeout=LINK_TIMEOUT,
                    follow_redirects=True,
                    limits=httpx.Limits(
                        max_connections=MAX_CONCURRENT,
                        max_keepalive_connections=MAX_CONCURRENT,
                    ),
                    headers={
                        "User-Agent": USER_AGENT,
                        # Ask for a page, not an API response — some hosts
                        # serve a 404 JSON stub to clients that don't say this.
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    },
                )
    return _http_client


async def close_link_client() -> None:
    """Close the shared client. Call on shutdown; safe to call twice."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


# ── findings ─────────────────────────────────────────────────────────


def _reason(status: LinkStatus) -> str:
    """The evidence, in words the owner can check in ten seconds."""
    if status.verdict == "gone":
        return f"the page no longer exists ({status.status_code})"
    if status.verdict == "dead_host":
        host = urlparse(status.url).hostname or "that domain"
        return f"it points at {host}, a domain that no longer exists"
    if status.verdict == "server_error":
        return f"the server answers {status.status_code} every time"
    if status.verdict == "cert":
        return "the browser blocks it with a security warning"
    return ""


def _too_noisy(results: list[LinkStatus], site_host: str) -> str:
    """Reasons to throw the whole run away rather than report any of it.

    This is the last line of defence and the one that matters most, because
    the failure modes it catches are the ones that produce *many* wrong
    findings at once — the exact shape that makes an email absurd.

      1. Half of everything failed. No real site is half-dead while its
         homepage loads; something is blocking us — rate limiting that kicked
         in partway through, a captive portal, our own network.
      2. Every failure is on the business's own host, and there are several.
         We know their homepage served us fine (we're reading its HTML), so a
         host that fails wholesale under a handful of requests is throttling
         us, not broken.
    """
    conclusive = [r for r in results if r.conclusive]
    if len(results) >= MIN_CHECKED:
        bad = sum(1 for r in results if r.broken or not r.conclusive)
        if bad / len(results) > NOISE_FLOOR:
            return f"{bad}/{len(results)} links failed — we are being blocked, not them"
    broken = [r for r in conclusive if r.broken]
    own = [r for r in broken if (urlparse(r.url).hostname or "").lower() == site_host]
    if len(own) >= 6 and len(own) == len(broken):
        return f"{len(own)} failures all on {site_host} — reads as throttling"
    return ""


def build_findings(links: list[Link], results: list[LinkStatus]) -> list[Finding]:
    """Turn verdicts into at most one finding. Pure — unit-testable offline.

    One finding rather than one per link, on purpose: the audit score is a sum
    of weights, and eight dead links in the same abandoned footer would
    otherwise outscore a site that doesn't work on a phone.
    """
    by_url = {link.url: link for link in links}
    broken = [r for r in results if r.broken and r.url in by_url]
    if not broken:
        return []

    site_host = ""
    internal = [link for link in links if link.internal]
    if internal:
        site_host = internal[0].host
    if reason := _too_noisy(results, site_host):
        # Deliberately silent. The comment is the log entry; on integration
        # this becomes a loom_logger.info so suppressions are visible.
        _ = reason
        return []

    # Lead with the link that costs the owner money. "Your menu link is dead"
    # is a sentence that gets a reply; "you have 3 broken links" is a sentence
    # that gets deleted.
    broken.sort(key=lambda r: (-by_url[r.url].value, r.url))
    worst = broken[0]
    link = by_url[worst.url]
    named = link.label or urlparse(link.url).path or link.url
    extra = f"; {len(broken) - 1} other dead link(s) on the site" if len(broken) > 1 else ""

    if link.value == 3:
        weight, label = 4, f"“{named}” link is dead"
    elif len(broken) > 1:
        weight, label = 3, f"{len(broken)} dead links"
    else:
        weight, label = 2, "A dead link on the site"

    return [
        Finding(
            code="broken_link",
            weight=weight,
            label=label[:80],
            detail=f"“{named}” goes to {worst.url} — {_reason(worst)}{extra}",
        )
    ]


# ── entry point ──────────────────────────────────────────────────────


async def check_links(
    pages: dict[str, str],
    *,
    client: httpx.AsyncClient | None = None,
    honour_robots: bool = True,
) -> list[Finding]:
    """Test the links on already-fetched pages; report only what's certainly dead.

    `pages` maps final page URL to the HTML that was already downloaded — the
    same contract as audit_response(html=...), and the reason this check adds
    no page fetches of its own. Pass `{home_url: home_html}` from
    _SiteFetcher.enrich, or the whole `pages` dict from harvest_site, which
    gives the deeper links a single-page audit never sees.

    Returns [] on anything short of certainty, including when the check itself
    fails. An empty list means "nothing to say", never "nothing is wrong".
    """
    if not pages:
        return []

    links: list[Link] = []
    for page_url, html in pages.items():
        links.extend(extract_links(html, page_url))
    links = select_links(links)
    if not links:
        return []

    owned = client or await _http()
    robots = _Robots(owned) if honour_robots else None

    # Per-host gate as well as a global one: the global limit alone would let
    # every slot land on the same small server the moment the external links
    # resolve fast.
    global_gate = asyncio.Semaphore(MAX_CONCURRENT)
    host_gates: dict[str, asyncio.Semaphore] = {}
    results: list[LinkStatus] = []

    async def one(link: Link) -> None:
        if robots and link.internal and not await robots.allows(link.url):
            return  # asked not to look; therefore nothing to claim
        gate = host_gates.setdefault(link.host, asyncio.Semaphore(MAX_PER_HOST))
        async with global_gate, gate:
            try:
                results.append(await _probe(owned, link))
            except Exception as e:  # a bug here must not fail the audit
                results.append(LinkStatus(link.url, "unknown", note=str(e)[:120]))

    tasks = [asyncio.create_task(one(link)) for link in links]
    done, pending = await asyncio.wait(tasks, timeout=TOTAL_BUDGET)
    for task in pending:
        # Out of budget. Whatever finished still counts; the rest are simply
        # unknown, which is the safe direction.
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    return build_findings(links, results)


# ── self-test: no network ────────────────────────────────────────────


_FAKE_PAGE = """
<html><body>
  <nav>
    <a href="/">Home</a>
    <a href="/menu">Our Menu</a>
    <a href="/contact">Contact</a>
    <a href="#top">Back to top</a>
    <a href="mailto:hi@shop.example">Email us</a>
    <a href="tel:+61255551234">Call</a>
    <a href="javascript:void(0)">Toggle</a>
  </nav>
  <main>
    <a href="https://www.instagram.com/shopexample">Follow us</a>
    <a href="https://oldbooking.example/reserve">Book a table</a>
    <a href="/menu#drinks">Drinks menu</a>
    <a href="/wp-admin/">admin</a>
    <a href="HTTPS://WWW.SHOP.EXAMPLE/Menu">Menu (uppercase host)</a>
  </main>
  <footer>
    <a href="/menu">Menu</a>
    <a href="/contact">Contact</a>
    <a href="https://partner.example/a">Partner</a>
    <a href="https://partner.example/b">Partner</a>
    <a href="https://partner.example/c">Partner</a>
  </footer>
</body></html>
"""


def _self_test() -> None:
    base = "https://www.shop.example/"
    links = select_links(extract_links(_FAKE_PAGE, base))
    urls = {link.url for link in links}

    # Non-HTTP schemes and bare anchors are not links to test.
    assert not any(u.startswith(("mailto", "tel", "javascript")) for u in urls)
    assert "https://www.shop.example/" in urls  # href="/" — the one real home link
    assert len(links) == len(urls)  # href="#top" produced nothing, not a duplicate home

    # Nav + footer repeat /menu and /contact; each survives once.
    assert sum(1 for u in urls if u.endswith("/menu")) == 1, urls
    assert "https://www.shop.example/menu" in urls
    # ...and the fragment was stripped rather than making a second entry.
    assert not any("#" in u for u in urls)

    # Case: host folded, path left alone. /Menu is a different file.
    assert "https://www.shop.example/Menu" in urls

    # Bot-walled and plumbing links dropped.
    assert not any("instagram" in u for u in urls)
    assert not any("wp-admin" in u for u in urls)

    # External host capped at MAX_EXTERNAL_PER_HOST.
    assert sum(1 for u in urls if "partner.example" in u) == MAX_EXTERNAL_PER_HOST

    # Valuation: menu/booking are money links, plain internal are not.
    value = {link.url: link.value for link in links}
    assert value["https://www.shop.example/menu"] == 3
    assert value["https://oldbooking.example/reserve"] == 3
    assert value["https://www.shop.example/"] == 2

    # Status mapping — the judgement calls, asserted.
    assert verdict_for_status(404) == "gone"
    assert verdict_for_status(410) == "gone"
    assert verdict_for_status(500) == "server_error"
    assert verdict_for_status(200) == "ok"
    assert verdict_for_status(301) == "ok"
    for blocked in (401, 403, 429, 451):
        assert verdict_for_status(blocked) == "blocked", blocked
    for quiet in (400, 405, 406, 415):
        assert verdict_for_status(quiet) == "unknown", quiet

    assert _transport_verdict(Exception("[SSL: CERTIFICATE_VERIFY_FAILED]")) == "cert"
    assert _transport_verdict(Exception("nodename nor servname provided")) == "dead_host"
    assert _transport_verdict(Exception("connect timed out")) == "unknown"

    # A dead menu link leads, and outranks a dead footer link.
    dead_menu = [
        LinkStatus("https://www.shop.example/menu", "gone", 404),
        LinkStatus("https://www.shop.example/", "ok", 200),
        LinkStatus("https://www.shop.example/contact", "ok", 200),
        LinkStatus("https://partner.example/a", "ok", 200),
        LinkStatus("https://partner.example/b", "ok", 200),
    ]
    findings = build_findings(links, dead_menu)
    assert len(findings) == 1
    assert findings[0].code == "broken_link"
    assert findings[0].weight == 4
    assert "Menu" in findings[0].label
    assert "404" in findings[0].detail

    # 403 and timeouts are never a finding.
    quiet_results = [
        LinkStatus("https://www.shop.example/menu", "blocked", 403),
        LinkStatus("https://www.shop.example/contact", "unknown"),
        LinkStatus("https://www.shop.example/", "ok", 200),
        LinkStatus("https://partner.example/a", "ok", 200),
    ]
    assert build_findings(links, quiet_results) == []

    # Kill switch: mass failure reports nothing at all.
    everything_dead = [
        LinkStatus(link.url, "gone", 404) for link in links
    ]
    assert build_findings(links, everything_dead) == [], "noise floor did not fire"

    # A single dead non-money link is a weak finding, not a headline.
    minor = [
        LinkStatus("https://partner.example/a", "gone", 404),
        LinkStatus("https://www.shop.example/menu", "ok", 200),
        LinkStatus("https://www.shop.example/", "ok", 200),
        LinkStatus("https://www.shop.example/contact", "ok", 200),
        LinkStatus("https://www.shop.example/Menu", "ok", 200),
        LinkStatus("https://partner.example/b", "ok", 200),
    ]
    small = build_findings(links, minor)
    assert len(small) == 1 and small[0].weight == 2, small

    print("self-test: ok — 30 assertions, no network")


# ── live probe ───────────────────────────────────────────────────────


async def _probe_live() -> None:
    """Run the real thing against real sites and print what it decides.

    Two halves: real homepages, where the right answer is almost always
    "nothing to report", and one hand-built page of known-dead links, which
    is the only way to prove the detection path fires end to end over the
    network rather than just in the self-test.
    """
    real = [
        "https://example.com",
        "https://www.iana.org",
        "https://httpbin.org",
    ]

    async with httpx.AsyncClient(
        timeout=LINK_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for url in real:
            started = time.perf_counter()
            try:
                home = await client.get(url)
            except httpx.HTTPError as e:
                print(f"\n{url}\n  could not fetch home page: {e}")
                continue

            html = home.text[:400_000]
            page_url = str(home.url)
            candidates = select_links(extract_links(html, page_url))
            findings = await check_links({page_url: html}, client=client)
            elapsed = time.perf_counter() - started
            print(f"\n{page_url}  ({len(html)} bytes)")
            print(f"  links selected: {len(candidates)}  in {elapsed:.1f}s")
            for link in candidates[:8]:
                kind = "int" if link.internal else "ext"
                print(f"    [{kind} v{link.value}] {link.label or '(no text)'} -> {link.url}")
            print(f"  findings: {len(findings)}")
            for finding in findings:
                print(f"    [{finding.code} w{finding.weight}] {finding.label}")
                print(f"      {finding.detail}")

        # Hand-built pages, shaped like a real one: mostly working links with
        # a single dead one among them. The first draft of this made three of
        # four links dead and correctly reported nothing — the noise floor
        # fired, because a site that is 75% dead is a site that is blocking
        # us. A realistic ratio is the only way to exercise the finding path.
        live = """
          <a href="/get">Home</a>
          <a href="/html">About us</a>
          <a href="/forms/post">Order online</a>
          <a href="/json">Gallery</a>
          <a href="/encoding/utf8">Our story</a>
          <a href="/status/200">Gift cards</a>"""

        rigged = {
            "one dead menu link": (
                "https://httpbin.org/",
                f'<html><body>{live}'
                '<a href="/loom-probe-menu-does-not-exist">Our Menu</a>'
                "</body></html>",
            ),
            "booking link with an expired certificate": (
                "https://httpbin.org/",
                f'<html><body>{live}'
                '<a href="https://expired.badssl.com/">Book a table</a>'
                "</body></html>",
            ),
            "booking link whose domain is gone": (
                "https://httpbin.org/",
                f'<html><body>{live}'
                '<a href="https://this-domain-is-gone-loom-probe.example/reserve">'
                "Book a table</a></body></html>",
            ),
        }

        for name, (base, html) in rigged.items():
            started = time.perf_counter()
            findings = await check_links({base: html}, client=client)
            print(f"\nrigged: {name}  in {time.perf_counter() - started:.1f}s")
            print(f"  findings: {len(findings)}")
            for finding in findings:
                print(f"    [{finding.code} w{finding.weight}] {finding.label}")
                print(f"      {finding.detail}")

    await close_link_client()


if __name__ == "__main__":  # pragma: no cover - manual probe
    _self_test()
    asyncio.run(_probe_live())
