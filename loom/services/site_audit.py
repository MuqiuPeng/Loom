"""Judge a small business's website from one page fetch.

The point isn't a full Lighthouse audit — it's answering one question cheaply:
is there something concrete and demonstrable wrong here, worth opening a
conversation about? Every finding is meant to be sayable out loud to a shop
owner without jargon ("your site doesn't work on a phone"), and verifiable by
them in ten seconds.

Higher `score` = better freelance lead. Findings are derived entirely from the
business's own page, so unlike Places data they carry no storage restriction.
"""

import re
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, computed_field

# Site builders whose free tier leaves the business on a shared subdomain —
# a reliable sign nobody has invested in the site.
_FREE_HOSTS = (
    "wixsite.com",
    "weebly.com",
    "business.site",  # Google's retired builder; still everywhere
    "godaddysites.com",
    "square.site",
    "mystrikingly.com",
    "jimdosite.com",
    "webnode.com",
    "blogspot.com",
    "wordpress.com",
)

# A social page used as the business's whole web presence.
_SOCIAL_HOSTS = (
    "facebook.com",
    "instagram.com",
    "linktr.ee",
    "linkedin.com",
    "yelp.com",
    "weibo.com",
    "xiaohongshu.com",
)

_PLACEHOLDER_RE = re.compile(
    r"under construction|coming soon|site is being|domain (is )?for sale|"
    r"buy this domain|parked (free )?by|网站建设中|敬请期待|此域名",
    re.I,
)
_VIEWPORT_RE = re.compile(r"<meta[^>]+name=[\"']viewport[\"']", re.I)
_DESCRIPTION_RE = re.compile(r"<meta[^>]+name=[\"']description[\"']", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_COPYRIGHT_RE = re.compile(r"(?:©|&copy;|copyright)[^0-9]{0,20}(\d{4})", re.I)

# Both spellings are in the wild; Facebook reads property=, a lot of themes
# emit name=, and either one produces a preview.
_OG_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:(?:title|image)[\"']", re.I
)
_TEL_RE = re.compile(r"href=[\"']tel:", re.I)
_ICON_RE = re.compile(r"<link[^>]+rel=[\"'][^\"']*icon", re.I)

_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# Australian numbers as a customer would see them written: landline with or
# without the area code's leading zero, mobile, and the 13/1300/1800 ranges.
# Deliberately strict — a loose pattern matches ABNs, dates and price lists,
# and a wrong "your number isn't clickable" is worse than a missed one.
_AU_PHONE_RE = re.compile(
    r"(?:\+?61[\s.-]?|\b0)(?:[2378][\s.-]?\d{4}[\s.-]?\d{4}"
    r"|4\d{2}[\s.-]?\d{3}[\s.-]?\d{3})"
    r"|\b1[38]00[\s.-]?\d{3}[\s.-]?\d{3}\b"
    r"|\b13[\s.-]?\d{2}[\s.-]?\d{2}\b"
)


def _text(html: str) -> str:
    """Visible copy only.

    Phone matching has to run on what a customer reads, not on the markup —
    tracking scripts and data attributes are full of digit runs that look like
    numbers and produce findings nobody can verify by looking at the page.
    """
    return _TAG_RE.sub(" ", _SCRIPT_RE.sub(" ", html))


# Inferred consent under the Spam Act's Schedule 2 cl 4 has several
# conditions, and one of them is that the published address carries no
# statement refusing unsolicited commercial messages. That condition was
# asserted in a docstring and implemented nowhere. A site that says this has
# withdrawn the only consent basis we have, so it must never be written to —
# this is a legal gate, not a lead-quality signal, and it produces no finding.
_NO_UNSOLICITED_RE = re.compile(
    r"no unsolicited|not accept unsolicited|do not accept unsolicited|"
    r"unsolicited (commercial |marketing |sales )?(e-?mail|messages|approaches|offers)"
    r"|no (cold[- ]call|spam|marketing|sales) (e-?mail|enquir|approach)"
    r"|not interested in (any )?(seo|web design|marketing) (services|offers|emails)",
    re.I,
)


def refuses_unsolicited(html: str) -> bool:
    """Whether the page asks not to be sent unsolicited commercial mail."""
    return bool(_NO_UNSOLICITED_RE.search(_text(html)))



def _digits(phone: str) -> str:
    """An Australian number reduced to something comparable.

    +61 2 9555 0142, (02) 9555 0142 and 0295550142 are one number written
    three ways, and Google and the site almost never agree on which.
    """
    kept = "".join(c for c in phone if c.isdigit() or c == "+")
    if kept.startswith("+61"):
        kept = "0" + kept[3:]
    elif kept.startswith("61") and len(kept) > 9:
        kept = "0" + kept[2:]
    return kept

# Pages this thin are a placeholder, a splash screen, or a broken render.
THIN_PAGE_BYTES = 2000
SLOW_LOAD_MS = 3000
STALE_YEARS = 3


class Finding(BaseModel):
    """One concrete, demonstrable problem."""

    code: str
    weight: int
    label: str
    detail: str = ""


class SiteAudit(BaseModel):
    """What one page fetch says about a small business's web presence."""

    url: str | None = None
    reachable: bool = True
    status_code: int | None = None
    load_ms: int | None = None
    findings: list[Finding] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def score(self) -> int:
        """Sum of finding weights — higher means a better lead.

        Computed rather than stored so it can't drift from the findings, and
        declared as a computed field so it survives serialisation to the UI.
        """
        return sum(f.weight for f in self.findings)

    @property
    def codes(self) -> list[str]:
        return [f.code for f in self.findings]


def audit_failure(url: str, kind: str, detail: str = "") -> SiteAudit:
    """The site is listed but doesn't load — the strongest signal there is."""
    known = {
        "ssl": Finding(
            code="ssl_invalid",
            weight=4,
            label="Invalid certificate",
            detail=detail or "Browsers block the page with a security warning",
        ),
        "dns": Finding(
            code="dead",
            weight=5,
            label="Domain doesn't resolve",
            detail=detail or "The site no longer loads at all",
        ),
        "timeout": Finding(
            code="timeout", weight=4, label="Timed out", detail=detail
        ),
    }
    finding = known.get(
        kind,
        Finding(code="unreachable", weight=5, label="Unreachable", detail=detail),
    )
    return SiteAudit(url=url, reachable=False, findings=[finding])


def audit_response(
    url: str,
    *,
    final_url: str,
    status_code: int,
    load_ms: int,
    html: str,
    google_phone: str | None = None,
    favicon_ok: bool | None = None,
) -> SiteAudit:
    """Everything judgeable from one successfully fetched page.

    `google_phone` and `favicon_ok` are optional because they come from
    outside the page: the first from the Places record, the second from a
    HEAD on /favicon.ico that only the caller can make. Left unset, the two
    checks that need them simply don't run — an audit that can't see the
    evidence must not guess at it.
    """
    audit = SiteAudit(
        url=final_url or url,
        reachable=True,
        status_code=status_code,
        load_ms=load_ms,
    )
    findings: list[Finding] = []
    host = (urlparse(final_url or url).hostname or "").lower()

    if status_code >= 400:
        findings.append(
            Finding(
                code="error_page",
                weight=5,
                label=f"Home page returns {status_code}",
                detail="The front door itself errors out",
            )
        )
        audit.findings = findings
        return audit

    if any(host == h or host.endswith("." + h) for h in _SOCIAL_HOSTS):
        findings.append(
            Finding(
                code="social_only",
                weight=4,
                label="Social page only",
                detail=f"The listed website is {host} — no site of their own",
            )
        )
    elif any(host.endswith(h) for h in _FREE_HOSTS):
        findings.append(
            Finding(
                code="free_subdomain",
                weight=2,
                label="Free builder subdomain",
                detail=f"Sits on {host} rather than their own domain",
            )
        )

    if _PLACEHOLDER_RE.search(html):
        findings.append(
            Finding(
                code="placeholder",
                weight=4,
                label="Placeholder page",
                detail="Still says under construction, or the domain is parked",
            )
        )

    if not (final_url or url).startswith("https://"):
        findings.append(
            Finding(
                code="no_https",
                weight=3,
                label="No HTTPS",
                detail="Chrome labels it “Not secure” in the address bar",
            )
        )

    if not _VIEWPORT_RE.search(html):
        findings.append(
            Finding(
                code="not_mobile_ready",
                weight=3,
                label="Unusable on a phone",
                detail="No viewport tag — phones get a shrunken desktop layout",
            )
        )

    if load_ms > SLOW_LOAD_MS:
        findings.append(
            Finding(
                code="slow",
                weight=2,
                label="Slow to load",
                detail=f"Home page took {load_ms / 1000:.1f}s",
            )
        )

    if len(html) < THIN_PAGE_BYTES:
        findings.append(
            Finding(
                code="thin",
                weight=2,
                label="Almost no content",
                detail="The home page is nearly empty",
            )
        )

    years = [int(y) for y in _COPYRIGHT_RE.findall(html) if y.isdigit()]
    if years:
        newest = max(years)
        if newest <= datetime.now().year - STALE_YEARS:
            findings.append(
                Finding(
                    code="stale",
                    weight=2,
                    label=f"Untouched since {newest}",
                    detail="Footer copyright hasn't moved in years",
                )
            )

    title = _TITLE_RE.search(html)
    if not title or not title.group(1).strip():
        findings.append(
            Finding(
                code="no_title",
                weight=1,
                label="No page title",
                detail="Search results and browser tabs can't show the business name",
            )
        )

    if not _DESCRIPTION_RE.search(html):
        findings.append(
            Finding(
                code="no_description",
                weight=1,
                label="No meta description",
                detail="Google's search snippet comes up empty",
            )
        )

    findings.extend(_contact_findings(html, google_phone))

    if not _OG_RE.search(html):
        findings.append(
            Finding(
                code="no_link_preview",
                weight=2,
                label="Link previews come up blank",
                detail=(
                    "No share tags — posting the address to Facebook or "
                    "WhatsApp shows an empty grey box instead of the shop"
                ),
            )
        )

    # Only when the caller actually looked. Absence of a <link rel="icon">
    # proves nothing on its own: browsers fall back to /favicon.ico, and most
    # sites have one sitting there unreferenced.
    if favicon_ok is False and not _ICON_RE.search(html):
        findings.append(
            Finding(
                code="no_favicon",
                weight=1,
                label="Blank icon in the browser tab",
                detail="No favicon, so the tab shows a plain sheet of paper",
            )
        )

    audit.findings = findings
    return audit


def _contact_findings(html: str, google_phone: str | None) -> list[Finding]:
    """What the page says about reaching them, and whether Google agrees.

    Two separate problems, both found from the same scan.

    The first is the tappable one. A number printed as plain text is a number
    a customer on a phone has to memorise and retype, and most won't — for a
    trade that is the whole funnel.

    The second is the mismatch. Loom is one of very few things that holds the
    Places record and the page at the same moment, so it can see a
    disagreement the owner cannot. Note the finding is written neutrally:
    which of the two is stale is not knowable from here, and only the owner
    can say.

    Deliberately NOT compared: the address. Postal formatting varies far too
    much to match reliably, and the address often lives on a contact page this
    audit never fetches — so every quiet suburb would get told its address was
    wrong. One check that holds up beats two that don't.
    """
    findings: list[Finding] = []
    on_page = _AU_PHONE_RE.findall(_text(html))
    if not on_page:
        # Silence here is not evidence. The number may be an image, or live
        # only on a contact page.
        return findings

    if not _TEL_RE.search(html):
        findings.append(
            Finding(
                code="phone_not_tappable",
                weight=3,
                label="Phone number can't be tapped",
                detail=(
                    "The number is printed as plain text — tapping it on a "
                    "phone does nothing instead of starting the call"
                ),
            )
        )

    if google_phone:
        wanted = _digits(google_phone)
        # Written forms differ constantly, so compare digits, and only claim a
        # mismatch when NOT ONE number on the page matches.
        if wanted and not any(_digits(p) == wanted for p in on_page):
            findings.append(
                Finding(
                    code="contact_mismatch",
                    weight=3,
                    label="Site and Google list different numbers",
                    detail=(
                        f"Google shows {google_phone.strip()}, the site shows "
                        f"{on_page[0].strip()} — customers are reaching one "
                        "of them and not the other"
                    ),
                )
            )

    return findings


def no_website_audit() -> SiteAudit:
    """Google lists the business but no website at all."""
    return SiteAudit(
        url=None,
        reachable=False,
        findings=[
            Finding(
                code="no_website",
                weight=5,
                label="No website at all",
                detail="Nothing listed on their Google Business Profile",
            )
        ],
    )
