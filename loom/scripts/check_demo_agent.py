"""Check the demo agent's verification rules.

The rules are the whole point of the agent, so they're tested without any
model in the loop: hand-written pages with known defects go in, the expected
violation codes must come out.

    python -m loom.scripts.check_demo_agent

Exits non-zero on any failure.
"""

import sys

from loom.services.demo_agent import check_html
from loom.services.demo_defaults import attribution_email
from loom.services.site_harvest import Harvest, MenuItem, Selection

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}")
        failures.append(label)


HARVEST = Harvest(
    images=["https://shop.example/hero.jpg", "https://shop.example/room.jpg"],
    menu=[
        MenuItem(name="Flat White", price="$4.50"),
        MenuItem(name="Bene", price="$22"),
    ],
    hours="Mon-Fri 7-3",
    about="A corner cafe.",
)

EMAIL = attribution_email() or "nobody@example.com"

HEAD = (
    '<meta name="robots" content="noindex, nofollow">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
)


def page(body: str, head: str = HEAD, attribution: bool = True) -> str:
    """A page that satisfies every rule except the one under test.

    The attribution block is included by default so a fixture doesn't trip
    missing_attribution while probing something else."""
    sign = f"<p>Built by tester — {EMAIL}</p>" if attribution else ""
    return f"<html><head>{head}</head><body>{body}{sign}{'x' * 600}</body></html>"


def codes(html: str, harvest: Harvest = HARVEST) -> list[str]:
    return [v.code for v in check_html(html, harvest)]


def main() -> int:
    print("demo agent rules:")

    clean = page(
        '<img src="https://shop.example/hero.jpg" alt="">'
        "<p>Flat White $4.50</p><p>Bene $22</p>"
    )
    check(codes(clean) == [], "a correct page raises nothing")

    check("missing_noindex" in codes(page("<p>hi</p>", head="")), "noindex required")
    check("missing_viewport" in codes(page("<p>hi</p>", head="")), "viewport required")
    check("empty" in codes("<html></html>"), "an empty page is caught")
    check("fenced" in codes("```html\n" + clean), "a markdown fence is caught")

    check(
        "external_script"
        in codes(page('<script src="https://cdn.example/x.js"></script>')),
        "external script is caught",
    )
    check(
        "external_stylesheet"
        in codes(page('<link rel="stylesheet" href="https://cdn.example/a.css">')),
        "external stylesheet is caught",
    )
    check(
        "external_stylesheet"
        in codes(page("<style>@import url(https://fonts.example/x);</style>")),
        "@import is caught",
    )

    check(
        "unknown_image"
        in codes(page('<img src="https://unsplash.example/stock.jpg">')),
        "an image outside the supplied set is caught",
    )
    check(
        codes(page('<img src="https://shop.example/room.jpg">')) == [],
        "a supplied image passes",
    )

    # The one that actually matters.
    invented = page("<p>Flat White $4.50</p><p>Smashed Avo $18.00</p>")
    check("invented_price" in codes(invented), "an invented price is caught")
    check(
        "$18.00" not in " ".join(v for v in codes(invented)),
        "the violation names a code, not the raw page",
    )
    check(
        codes(page("<p>Bene $22</p>")) == [],
        "a price present in the harvest passes",
    )

    # Selection narrows what counts as supported.
    narrowed = HARVEST.model_copy(deep=True)
    narrowed.selection = Selection(menu=["Bene"], images=["https://shop.example/room.jpg"])
    check(
        "invented_price" in codes(page("<p>Flat White $4.50</p>"), narrowed),
        "a de-selected item's price no longer counts as supported",
    )
    check(
        "unknown_image"
        in codes(page('<img src="https://shop.example/hero.jpg">'), narrowed),
        "a de-selected image is rejected",
    )

    check(
        "unprefixed_backdrop_filter"
        in codes(page("<style>.g{backdrop-filter:blur(16px)}</style><p>x</p>")),
        "backdrop-filter without the -webkit- prefix is caught",
    )
    check(
        "unprefixed_backdrop_filter"
        not in codes(page(
            "<style>.g{backdrop-filter:blur(16px);"
            "-webkit-backdrop-filter:blur(16px)}</style><p>x</p>"
        )),
        "the prefixed pair passes",
    )

    # Placeholder photography has to be declared on the page.
    stocked = HARVEST.model_copy(deep=True)
    stocked.images = ["https://stock.example/a.jpg"]
    with_img = page('<img src="https://stock.example/a.jpg">')
    check(
        "missing_stock_note"
        in [v.code for v in check_html(with_img, stocked, stock_used=True)],
        "undeclared placeholder photography is caught",
    )
    check(
        "missing_stock_note"
        not in [v.code for v in check_html(with_img, stocked, stock_used=False)],
        "the note is not demanded when the photos are the business's own",
    )

    check(
        "preamble"
        in [
            v.code
            for v in check_html(
                "Here's the corrected HTML:\n" + clean, HARVEST
            )
        ],
        "commentary before the document is caught",
    )

    check(
        "missing_attribution" in codes(page("<p>hi</p>", attribution=False)),
        "a page with no sender contact is caught",
    )

    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
