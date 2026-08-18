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


async def image_pick_checks() -> None:
    """The ranker's contract, without looking at a single picture.

    What the model decides needs eyes and cannot be asserted here. What it is
    allowed to decide can: a demo must never be handed a URL the crawler did
    not find, and must never be left with no pictures because a model call
    timed out.
    """
    from loom.services.image_pick import Ranked, _clean, rank

    print("\n── image ranking ──")

    urls = ["a.jpg", "b.jpg", "c.jpg"]

    check(_clean([2, 0], 3) == [2, 0], "the model's order is the order")
    check(_clean([1, 1, 0], 3) == [1, 0], "a repeated index is taken once")
    check(_clean([9, -1, 0], 3) == [0], "an out-of-range index is dropped")

    class Stub:
        def __init__(self, result=None, boom=False):
            self.result, self.boom = result, boom

        async def extract_model(self, *a, **k):
            if self.boom:
                raise RuntimeError("the merchant's server refused the fetch")
            return self.result

    ranked = await rank(urls, claude=Stub(Ranked(keep=[2, 0])))
    check(ranked == ["c.jpg", "a.jpg"], "indices become the URLs they stood for")

    # The failure that must not take a build down with it.
    check(
        await rank(urls, claude=Stub(boom=True)) == urls,
        "an unreachable image leaves the crawl order alone",
    )
    check(
        await rank(urls, claude=Stub(Ranked(keep=[]))) == urls,
        "rejecting every photo is not believed",
    )
    # A model cannot introduce a picture, only choose among the ones found.
    check(
        set(await rank(urls, claude=Stub(Ranked(keep=[99, 1])))) <= set(urls),
        "no URL comes back that the crawler did not find",
    )
    check(
        await rank(["only.jpg"], claude=Stub(boom=True)) == ["only.jpg"],
        "one image is not worth a model call",
    )


def cli_checks() -> None:
    """The CLI's shape, and the one command it must not have."""
    from click.testing import CliRunner

    from loom.cli_scout import scout

    print("\n-- scout cli --")

    names = set(scout.commands)
    for wanted in ("leads", "show", "harvest", "audit", "draft", "queue", "doctor"):
        check(wanted in names, f"`scout {wanted}` exists")

    # The whole point of the module docstring. Sending goes through a person
    # marking a row Approved and then an endpoint; a second path is the route
    # around that mailer already warns about.
    for forbidden in ("send", "send-approved", "mail", "contact"):
        check(forbidden not in names, f"`scout {forbidden}` does not exist, and should not")

    # Every command has to survive --help without importing a database.
    runner = CliRunner()
    for name in sorted(names):
        result = runner.invoke(scout, [name, "--help"])
        check(result.exit_code == 0, f"`scout {name} --help` works")


def text_and_score_checks() -> None:
    """Two facts that reach a shop owner, and used to reach them mangled."""
    from loom.services.company_scout import _text
    from loom.services.site_audit import audit_response

    print("\n-- extracted text and score --")

    # site_title feeds the panel and, when Google has no name, the greeting of
    # a cold email. "Dulwich Hill &ndash; Cafe Calibre" was what it held.
    check(_text("Venue &ndash; Dulwich Hill") == "Venue – Dulwich Hill",
          "an HTML entity is decoded, not carried through")
    check(_text("Bob &amp; Sons") == "Bob & Sons", "and so is an ampersand")
    check(_text("Two\n  lines   spaced") == "Two lines spaced",
          "newlines and runs collapse to single spaces")
    check(_text("<b>Coffee</b> Bar") == "Coffee Bar", "tags still go")

    # The audit carries its own total; the column exists only so a list can
    # sort. They disagreed on a real lead — score 1 over findings of 3, 3, 1.
    page = "<html><head><title>x</title></head><body>" + ("y" * 3000) + "</body></html>"
    audit = audit_response("https://x.test/", final_url="https://x.test/",
                           status_code=200, load_ms=300, html=page)
    check(audit.score == sum(f.weight for f in audit.findings),
          "an audit's score is the sum of what it found")


def harvest_regression_checks() -> None:
    """A thinner harvest must not replace a thicker one."""
    from loom.services.site_harvest import Harvest, MenuItem, _images, is_regression

    print("\n-- harvest regressions --")

    stored = {"menu": [{"name": "a"}] * 36, "images": ["i"] * 3,
              "pages_read": ["p"] * 3, "about": "who we are"}
    full = Harvest(menu=[MenuItem(name="a")] * 36, images=["i"] * 3,
                   pages_read=["p"] * 3, about="who we are")

    check(not is_regression(None, Harvest()), "the first harvest is always kept")
    check(not is_regression(stored, full), "an identical re-harvest is kept")
    check(not is_regression(stored, full.model_copy(update={
        "menu": [MenuItem(name="a")] * 40})), "more is kept")

    # The one that actually happened: 36 items to nothing on identical code.
    check(is_regression(stored, full.model_copy(update={"menu": []})),
          "a menu that vanished is a failed render, not news")
    check(is_regression(stored, full.model_copy(update={"about": None})),
          "so is prose that was there a minute ago")
    check(is_regression(stored, Harvest(error="home page unreadable")),
          "an errored harvest never replaces a good one")

    # Field by field, not on a total: gaining images does not pay for a menu.
    traded = full.model_copy(update={"menu": [], "images": ["i"] * 99})
    check(is_regression(stored, traded), "a trade is not an improvement")

    # The hero on a page built entirely of CSS backgrounds. The delimiters are
    # HTML-escaped because the style attribute is itself quoted.
    css = '<div style="background: url(&quot;http://s.test/hero.jpg&quot;) 50%"></div>'
    check(_images(css, "http://s.test/") == ["http://s.test/hero.jpg"],
          "an escaped-quote CSS background yields a usable URL")


def geography_checks() -> None:
    """Leads must be in the country that was searched, and URLs must be URLs."""
    from loom.services.company_scout import Candidate, _in_country
    from loom.services.site_harvest import _images

    print("\n-- geography and malformed URLs --")

    def at(address):
        return Candidate(provider="google", place_id="p",
                         google_name="Shop", google_address=address)

    au = "66 Constitution Rd, Dulwich Hill NSW 2203, Australia"
    us = "3820 E Main St #9, Mesa, AZ 85205, USA"

    check(_in_country(at(au), "AU"), "an Australian shop passes an Australian search")
    check(not _in_country(at(us), "AU"), "a shop in Arizona does not")
    check(not _in_country(at("1 Queen St, Auckland 1010, New Zealand"), "AU"),
          "nor does one across the Tasman")
    check(_in_country(at(us), None), "with no country searched, nothing is dropped")
    check(_in_country(at("a line with no comma"), "AU"),
          "an address naming no country is not evidence of a foreign one")

    # The one that reached the panel as a broken thumbnail: the match ran out
    # of the attribute and into a script, and urljoin made a URL of the wreck.
    page = (
        '<html><body><img src=\'"http:/pvgrinds.com/images/a.jpg\'>'
        '<img src="/images/real.jpg"></body></html>'
    )
    found = _images(page, "http://pvgrinds.com/")
    check(found == ["http://pvgrinds.com/images/real.jpg"],
          "a URL with a quote in it is dropped and the sound one kept")
    check(not any("://" in u.split("://", 1)[1] for u in found),
          "and nothing comes out with two schemes in it")


def menu_doc_checks() -> None:
    """Which links are the menu, and which only look like it."""
    from loom.services import menu_doc
    from loom.services.site_audit import audit_response

    print("\n-- menu as a file --")

    base = "https://shop.example/"
    def find(html):
        return menu_doc.find(html, base)

    # The real one, typo and all: the anchor says Menu, the file says "manu".
    real = '<a href="https://cdn.shopify.com/s/files/new_manu_all_items.pdf?v=1">Menu</a>'
    check(find(real) == ["https://cdn.shopify.com/s/files/new_manu_all_items.pdf?v=1"],
          "the anchor text finds it even when the filename is misspelled")

    check(find('<a href="/menus/winter.pdf">Download</a>'),
          "the address finds it when the anchor says nothing useful")
    check(find('<a href="/drinks-list.jpg">Drinks List</a>'),
          "a photographed menu counts")

    check(not find('<a href="/pages/menu">Menu</a>'),
          "a menu that is a page is not a menu that is a file")
    check(not find('<a href="/terms.pdf">Terms &amp; Conditions</a>'),
          "an unrelated PDF is not the menu")
    check(not find('<a href="/order-online">Order Online</a>'),
          "ordering is not the menu, and the page hints would have said it was")

    # The finding the outreach email leads on.
    page = "<html><head><title>Cafe</title></head><body>" + ("x" * 3000) + real + "</body></html>"
    codes = {f.code: f for f in audit_response(
        base, final_url=base, status_code=200, load_ms=300, html=page).findings}
    check("menu_is_a_file" in codes, "a file menu is a finding")
    check(codes["menu_is_a_file"].weight >= 3,
          "and weighs enough to open an email, which is the point of it")
    clean = page.replace(real, '<a href="/pages/menu">Menu</a>')
    check("menu_is_a_file" not in {f.code for f in audit_response(
        base, final_url=base, status_code=200, load_ms=300, html=clean).findings},
        "a normal menu page raises nothing")


async def render_fallback_checks() -> None:
    """The rendering fallback's contract, with no browser in the room.

    CI has no Chromium by design, so what is asserted here is the behaviour
    that matters when there isn't one: the harvest keeps whatever HTML it
    fetched and nothing raises.
    """
    from loom.services.page_render import Renderer, is_thin

    print("\n-- browser fallback --")

    check(is_thin(""), "an empty document is a shell")
    check(is_thin("Loading..."), "a spinner is a shell")
    check(not is_thin("word " * 200), "a page with words on it is not")

    renderer = Renderer()
    renderer._failed = True  # what a machine with no Playwright looks like
    check(
        await renderer.html_of("https://example.invalid") == "",
        "no browser returns nothing rather than raising",
    )
    await renderer.close()

    # The caller's rule: rendering is an improvement on the HTML it holds, so
    # an empty render must leave that HTML in place.
    from loom.services.site_harvest import _thicken

    shell = "<html><body>Loading...</body></html>"
    kept = await _thicken(renderer, "https://example.invalid", shell)
    check(kept == shell, "a failed render keeps the fetched page")

    full = "<html><body>" + ("word " * 300) + "</body></html>"
    check(
        await _thicken(renderer, "https://example.invalid", full) == full,
        "a page with text is never re-fetched",
    )


async def main() -> int:
    audit_checks()
    email_checks()
    await enrichment_checks()
    await image_pick_checks()
    cli_checks()
    text_and_score_checks()
    harvest_regression_checks()
    geography_checks()
    menu_doc_checks()
    await render_fallback_checks()
    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
