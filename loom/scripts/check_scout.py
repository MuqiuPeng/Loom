"""Check for the site audit and the scout enrichment path.

Fully offline: a stubbed transport serves purpose-built bad websites and the
findings are asserted against them. No Places calls, no billing, no traffic to
anyone's real server.

    python -m loom.scripts.check_scout

Exits non-zero on any failure.
"""

import asyncio
import sys
from datetime import datetime

import httpx

from loom.services.company_scout import (
    Candidate,
    _clean_emails,
    _SiteFetcher,
    summarise,
)
from loom.services.site_audit import (
    SiteAudit,
    audit_failure,
    audit_response,
    no_website_audit,
)

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}")
        failures.append(label)


GOOD_PAGE = """<html><head><title>Marrickville Coffee</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Specialty coffee in Marrickville">
<meta property="og:title" content="Marrickville Coffee">
</head><body>%s
<a href="mailto:hello@marrickvillecoffee.com.au">Email us</a>
<a href="tel:0295550142">02 9555 0142</a>
<footer>&copy; 2026 Marrickville Coffee</footer></body></html>""" % ("padding " * 400)

DATED_PAGE = """<html><head><title>Corner Store</title></head><body>%s
<footer>&copy; 2016 Corner Store</footer></body></html>""" % ("filler " * 400)

PLACEHOLDER_PAGE = "<html><head><title>Welcome</title></head><body>Coming soon</body></html>"


def audit_checks() -> None:
    print("site audit:")

    good = audit_response(
        "https://ok.example",
        final_url="https://ok.example",
        status_code=200,
        load_ms=400,
        html=GOOD_PAGE,
    )
    check(good.score == 0, "a healthy site produces no findings")

    dated = audit_response(
        "http://old.example",
        final_url="http://old.example",
        status_code=200,
        load_ms=4200,
        html=DATED_PAGE,
    )
    check("no_https" in dated.codes, "plain http is flagged")
    check("not_mobile_ready" in dated.codes, "missing viewport is flagged")
    check("slow" in dated.codes, "a 4.2s load is flagged")
    check("no_description" in dated.codes, "missing meta description is flagged")
    check("stale" in dated.codes, f"copyright 2016 is stale in {datetime.now().year}")
    check(dated.score > good.score, "the dated site scores as the better lead")

    failure_mode_checks(good)
    contact_checks()


def contact_checks() -> None:
    """The phone findings, which are the ones most able to embarrass us.

    Every case below is a wrong finding we would otherwise have emailed to a
    real business: an ABN read as a phone number, a number inside a tracking
    script, or a "your number is wrong" sent to someone whose number is right
    and merely written with brackets.
    """
    head = (
        '<meta name="viewport" content="width=device-width">'
        '<title>Ferro Plumbing</title>'
        '<meta name="description" content="d">'
        '<meta property="og:title" content="Ferro">'
    )

    def codes(body: str, **kw: object) -> list[str]:
        return audit_response(
            "https://x.example",
            final_url="https://x.example",
            status_code=200,
            load_ms=400,
            html=head + body,
            **kw,  # type: ignore[arg-type]
        ).codes

    print("\ncontact findings:")
    check("phone_not_tappable" in codes("<p>Call 02 9555 0142</p>"),
          "a plain-text number is flagged")
    check("phone_not_tappable" in codes("<p>0412 345 678</p>"), "mobile is flagged")
    check("phone_not_tappable" in codes("<p>1300 975 111</p>"), "1300 is flagged")
    check("phone_not_tappable" not in codes('<a href="tel:0295550142">ring</a>'),
          "a tel: link is not flagged")
    check("phone_not_tappable" not in codes("<p>Open Tue to Sun</p>"),
          "no number on the page means no finding")

    check("phone_not_tappable" not in codes("<p>ABN 51 824 753 556</p>"),
          "an ABN is not mistaken for a phone number")
    check("phone_not_tappable" not in codes("<p>Est. 1987, 25 years on.</p>"),
          "a year is not mistaken for a phone number")
    check("phone_not_tappable" not in
          codes('<script>var uid="0412345678";</script><p>Hi</p>'),
          "digits inside a script are not read as page content")

    check("contact_mismatch" in
          codes("<p>02 9555 0142</p>", google_phone="(02) 9555 9999"),
          "a genuinely different number is flagged")
    check("contact_mismatch" not in
          codes("<p>02 9555 0142</p>", google_phone="(02) 9555 0142"),
          "the same number written differently is not a mismatch")
    check("contact_mismatch" not in
          codes("<p>+61 2 9555 0142</p>", google_phone="02 9555 0142"),
          "+61 and 0 forms are the same number")
    check("contact_mismatch" not in
          codes("<p>Sales 02 9555 0142 or yard 02 9555 9999</p>",
                google_phone="02 9555 9999"),
          "any number on the page counts, not just the first")
    check("contact_mismatch" not in codes("<p>02 9555 0142</p>"),
          "without the Places phone no claim is made")

    def bare(html: str, **kw: object) -> list[str]:
        """Audit a page carrying none of the head tags."""
        return audit_response(
            "https://x.example",
            final_url="https://x.example",
            status_code=200,
            load_ms=400,
            html=html,
            **kw,  # type: ignore[arg-type]
        ).codes

    check("no_link_preview" in bare("<title>t</title><p>hi</p>"),
          "a page with no share tags is flagged")
    check("no_link_preview" not in codes("<p>hi</p>"),
          "a page carrying og:title is not flagged")
    check("no_favicon" not in
          bare('<link rel="icon" href="/f.png">', favicon_ok=False),
          "a declared icon beats a missing default file")
    check("no_favicon" in bare("<title>t</title>", favicon_ok=False),
          "no icon tag and no default file is flagged")
    check("no_favicon" not in bare("<title>t</title>"),
          "an unchecked favicon makes no claim")


def failure_mode_checks(good: SiteAudit) -> None:
    """The pages that fail outright, rather than merely fail well."""
    placeholder = audit_response(
        "https://soon.example",
        final_url="https://soon.example",
        status_code=200,
        load_ms=200,
        html=PLACEHOLDER_PAGE,
    )
    check("placeholder" in placeholder.codes, "'coming soon' is flagged")
    check("thin" in placeholder.codes, "a near-empty page is flagged")

    social = audit_response(
        "https://facebook.com/someshop",
        final_url="https://facebook.com/someshop",
        status_code=200,
        load_ms=300,
        html=GOOD_PAGE,
    )
    check("social_only" in social.codes, "a facebook page as the website is flagged")

    free = audit_response(
        "https://shop.wixsite.com/x",
        final_url="https://shop.wixsite.com/x",
        status_code=200,
        load_ms=300,
        html=GOOD_PAGE,
    )
    check("free_subdomain" in free.codes, "a free builder subdomain is flagged")

    broken = audit_response(
        "https://err.example",
        final_url="https://err.example",
        status_code=500,
        load_ms=300,
        html="",
    )
    check(broken.codes == ["error_page"], "a 500 short-circuits to one finding")

    check(audit_failure("https://x.example", "ssl").codes == ["ssl_invalid"], "ssl failure")
    check(audit_failure("https://x.example", "dns").codes == ["dead"], "dns failure")
    check(no_website_audit().score == 5, "no website at all is the strongest signal")

    check(
        "score" in good.model_dump(mode="json"),
        "score is serialised for the UI",
    )


async def enrichment_checks() -> None:
    print("\nenrichment:")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "dead.example":
            raise httpx.ConnectError("nodename nor servname provided")
        if path == "/careers":
            return httpx.Response(
                200, text='<a href="mailto:jobs@ok.example">jobs</a>'
            )
        return httpx.Response(
            200,
            text=GOOD_PAGE.replace(
                "</body>", '<a href="/careers">Careers</a></body>'
            ),
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        fetcher = _SiteFetcher(client)

        healthy = await fetcher.enrich(
            Candidate(place_id="a", google_name="OK", google_website="https://ok.example")
        )
        check(healthy.site_title == "Marrickville Coffee", "title read from the page")
        check("hello@marrickvillecoffee.com.au" in healthy.emails, "mailto harvested")
        check(healthy.careers_url is not None, "careers link found")
        check("jobs@ok.example" in healthy.emails, "careers page email harvested")
        check(healthy.opportunity == 0, "healthy site is not a freelance lead")

        dead = await fetcher.enrich(
            Candidate(place_id="b", google_name="Dead", google_website="https://dead.example")
        )
        check(dead.audit is not None and "dead" in dead.audit.codes, "dns failure audited")
        check(dead.opportunity >= 5, "a dead site is a top lead")

        siteless = await fetcher.enrich(Candidate(place_id="c", google_name="No Site"))
        check(siteless.opportunity == 5, "no website scores without any fetch")

        stats = summarise([healthy, dead, siteless])
        check(stats["without_website"] == 1, "summary counts the siteless one")
        check(stats["by_finding"].get("dead") == 1, "summary counts findings")

        # robots.txt disallow — we must not judge a page we didn't read.
        def blocked(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            return httpx.Response(200, text=GOOD_PAGE)

        async with httpx.AsyncClient(transport=httpx.MockTransport(blocked)) as strict:
            polite = await _SiteFetcher(strict).enrich(
                Candidate(place_id="d", google_name="Strict", google_website="https://no.example")
            )
            check(polite.audit is None, "robots.txt disallow leaves no audit")
            check(polite.fetch_error == "blocked by robots.txt", "and says why")


def email_checks() -> None:
    """Every case here came out of a real run on Marrickville cafes."""
    print("\nemail cleaning:")

    cleaned = _clean_emails(
        [
            "hello@eatozzo.com",
            "hello@eatozzo.com\\,",  # escaped fragment from embedded JSON
            "ankit@eatozzo.com",
        ]
    )
    check(cleaned == ["hello@eatozzo.com", "ankit@eatozzo.com"], "escape artifact folded in")

    twins = _clean_emails(["hello@thegiantbean.com", "hello@thegiantbean.com.au"])
    check(twins == ["hello@thegiantbean.com.au"], "truncated twin dropped")

    check(_clean_emails(["user@domain.com"]) == [], "template placeholder dropped")
    check(
        _clean_emails(["you@example.com", "info@yourdomain.com"]) == [],
        "other theme placeholders dropped",
    )
    check(
        _clean_emails(["coffeecorner.burwood@gmail.com"])
        == ["coffeecorner.burwood@gmail.com"],
        "a real gmail address survives",
    )
    check(
        _clean_emails(["hello@marrickvillecoffee.com.au"])
        == ["hello@marrickvillecoffee.com.au"],
        "a normal address is untouched",
    )


async def main() -> int:
    audit_checks()
    email_checks()
    await enrichment_checks()
    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
