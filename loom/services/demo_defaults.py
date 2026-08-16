"""Fallbacks for the parts of a demo the harvest couldn't fill.

The distinction this module exists to hold:

    structure   → may be defaulted. A Menu heading with "your menu goes here"
                  shows the shape of the finished thing and gives the owner an
                  obvious reason to reply.
    facts       → never. A fabricated dish or price is spotted instantly by
                  the one person who knows the business, and the pitch is over.
                  check_html()'s invented_price rule stays in force.

There is a third thing every demo needs and none of them had: a line saying
who built it and how to reply. A preview nobody can respond to is wasted work,
and an unattributed page carrying someone's name and photos is worse than
wasted.

Content lives in config/demo_defaults.json so it can be reworded without
touching code or restarting anything.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from loom.services.site_harvest import Harvest

CONFIG_PATH = Path("config/demo_defaults.json")

FALLBACK: dict[str, Any] = {
    "attribution": {
        "built_by": "",
        "email": "",
        "headline": "This preview was built for you",
        "body": "An independent mock-up — not affiliated with the business.",
        "cta": "Reply if you'd like the real thing",
    },
    "placeholder_note": "Sample layout",
    "sections": {},
    "palettes": {"default": {"ink": "#1c1c1e", "paper": "#f8f7f5", "accent": "#3b6ea5"}},
    "no_image_treatment": "Build the hero from typography and colour alone.",
}


@lru_cache(maxsize=1)
def _load(mtime: float) -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return FALLBACK


def defaults() -> dict[str, Any]:
    """Current config, re-read whenever the file changes on disk."""
    try:
        return _load(CONFIG_PATH.stat().st_mtime)
    except OSError:
        return FALLBACK


def palette_for(primary_type: str | None) -> dict[str, str]:
    palettes = defaults().get("palettes", FALLBACK["palettes"])
    if primary_type:
        for key, value in palettes.items():
            if key != "default" and key in primary_type.lower():
                return value
    return palettes.get("default", FALLBACK["palettes"]["default"])


def completeness(harvest: Harvest) -> dict[str, bool]:
    """Which sections have real material behind them."""
    selection = harvest.selection
    return {
        "menu": bool(selection.menu_from(harvest.menu)),
        "hours": bool(harvest.hours) and selection.use_hours,
        "location": bool(harvest.address),
        "gallery": bool(selection.images_from(harvest.images)),
        "about": bool(harvest.about) and selection.use_about,
    }


def guidance(harvest: Harvest, primary_type: str | None) -> str:
    """The block appended to the build prompt.

    Names each missing section explicitly and says what to put there, so the
    model fills gaps with a marked placeholder instead of quietly inventing
    something — which is what an unguided model does when the facts run out.
    """
    config = defaults()
    have = completeness(harvest)
    palette = palette_for(primary_type)
    note = config.get("placeholder_note", FALLBACK["placeholder_note"])
    attribution = {**FALLBACK["attribution"], **config.get("attribution", {})}

    lines = [
        "",
        "NEVER STATE A LOCATION that was not given to you above — not a",
        "suburb, city or region, however obvious it seems from the name.",
        "A business called 'The Gong Cafe' need not be in Wollongong.",
        "",
        "PALETTE (use these, they suit the trade):",
        f"  ink {palette['ink']} · paper {palette['paper']} · accent {palette['accent']}",
    ]

    if not have["about"]:
        # A generic tagline breaks no rule — it names no price, no address —
        # but it still puts words in the owner's mouth, and across three
        # variants side by side they'd read three different invented mottos.
        lines += [
            "",
            "NO DESCRIPTION AVAILABLE:",
            "  Do not write a tagline, motto or strapline. Nothing that claims",
            "  to speak for the business. The hero carries the name and",
            "  nothing else.",
        ]

    if not have["gallery"]:
        note = stock_note()
        if harvest.images and note:
            # Placeholder photography is in play — say so on the page. Silent
            # stock reads as "here is your shop", which it is not.
            lines += [
                "",
                "PHOTOGRAPHY IS PLACEHOLDER:",
                "  The supplied images are stock, not this business's own.",
                "  Use them freely for atmosphere — hero, gallery, section",
                "  breaks — but they must never be captioned or framed as if",
                "  they show these premises, this food or these staff.",
                f'  Print the line "{note}" once, small and quiet, beside the',
                "  first place a photograph appears.",
            ]
        else:
            lines += ["", "NO PHOTOGRAPHS AVAILABLE:", "  " + config.get(
                "no_image_treatment", FALLBACK["no_image_treatment"])]

    missing = [k for k, v in have.items() if not v and k in config.get("sections", {})]
    wanted = [
        k for k in missing
        if config["sections"][k].get("include_when_missing")
    ]
    showcase = config.get("capability_showcase", {})

    if wanted:
        lines += ["", "SECTIONS WITH NO REAL DATA:", "  " + showcase.get("intro", "")]
        for key in wanted:
            section = config["sections"][key]
            lines.append(f'  {section.get("heading", key)} — build it out with:')
            for row in section.get("sample_rows", []):
                lines.append(f"      · {row}")
            if section.get("sample_groups"):
                lines.append(
                    "      grouped under: "
                    + ", ".join(section["sample_groups"])
                )
        lines += [
            f"  {showcase.get('sample_row_rule', '')}",
            f'  Label each sampled section quietly — a small tag reading "{note}".',
            "  Never invent a dish, a price, an hour or an address.",
        ]

    # The thinner the harvest, the more the page has to earn attention on
    # craft alone — an empty page tells a shop with no website that they have
    # nothing, when the whole pitch is what they could have.
    thin = sum(1 for v in have.values() if v) <= 1
    if thin and showcase.get("techniques"):
        lines += [
            "",
            "THIS BUSINESS HAS ALMOST NO CONTENT ONLINE — the page must carry",
            "itself on execution. Use several of these, chosen to suit the",
            "direction (all are CSS-only; no JavaScript is permitted):",
        ]
        lines += [f"  · {technique}" for technique in showcase["techniques"]]

    strip = showcase.get("strip") or {}
    if strip.get("items"):
        lines += [
            "",
            f'CAPABILITY STRIP — include it, headed "{strip.get("heading", "")}":',
        ]
        lines += [f"  · {item}" for item in strip["items"]]
        lines.append(f"  ({strip.get('note', '')})")

    lines += [
        "",
        "CLOSING BLOCK (required, last section before the footer):",
        f'  Heading: "{attribution["headline"]}"',
        f'  Body: "{attribution["body"]}"',
        f'  Signed: {attribution["built_by"]} — {attribution["email"]}',
        f'  Call to action: "{attribution["cta"]}"',
        "  Keep it quiet and small; it is a note from a person, not a banner ad.",
    ]
    return "\n".join(lines)


STOCK_PATH = Path("config/demo_stock.json")


@lru_cache(maxsize=1)
def _load_stock(mtime: float) -> dict[str, Any]:
    try:
        return json.loads(STOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sets": {}, "stock_note": ""}


def stock() -> dict[str, Any]:
    try:
        return _load_stock(STOCK_PATH.stat().st_mtime)
    except OSError:
        return {"sets": {}, "stock_note": ""}


def stock_images(primary_type: str | None) -> list[str]:
    """Placeholder photographs for a trade, or an empty list.

    Only ever used when the business has none of its own. Facts stay theirs;
    the pictures are set dressing, labelled as such on the page.
    """
    config = stock()
    sets = config.get("sets", {})
    if not sets:
        return []
    haystack = (primary_type or "").lower()
    chosen = sets.get("default", [])
    for key, ids in sets.items():
        if key != "default" and key in haystack:
            chosen = ids
            break
    base = config.get("base", "")
    params = config.get("params", "")
    return [f"{base}{photo_id}{params}" for photo_id in chosen]


def stock_note() -> str:
    return stock().get("stock_note", "")


STYLES_PATH = Path("config/demo_styles.json")


@lru_cache(maxsize=1)
def _load_styles(mtime: float) -> dict[str, Any]:
    try:
        return json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"directions": {}, "universal_rules": []}


def styles() -> dict[str, Any]:
    try:
        return _load_styles(STYLES_PATH.stat().st_mtime)
    except OSError:
        return {"directions": {}, "universal_rules": []}


def pick_direction(primary_type: str | None, override: str | None = None) -> tuple[str, dict]:
    """Choose an art direction for this business.

    Matched on the Places primary type, which is what the trade actually is —
    a wine bar and a burger joint should not come out looking the same, and
    left to itself the model gives them the same centred stack.
    """
    directions = styles().get("directions", {})
    if not directions:
        return "", {}
    if override and override in directions:
        return override, directions[override]
    haystack = (primary_type or "").lower()
    for key, direction in directions.items():
        if any(hint in haystack for hint in direction.get("suits", [])):
            return key, direction
    # An unmatched trade gets the most broadly applicable direction, not
    # whichever happens to be first in the file.
    fallback = styles().get("default_direction", "modern_grid")
    if fallback in directions:
        return fallback, directions[fallback]
    first = next(iter(directions))
    return first, directions[first]


def art_direction(primary_type: str | None, override: str | None = None) -> str:
    """The design half of the build prompt."""
    key, direction = pick_direction(primary_type, override)
    if not direction:
        return ""
    fonts = direction.get("fonts", {})
    lines = [
        "",
        f"ART DIRECTION — {direction.get('label', key)} (follow it exactly):",
        f"  Display font stack: {fonts.get('display', 'system sans')}",
        f"  Body font stack: {fonts.get('body', 'system sans')}",
    ]
    lines += [f"  {rule}" for rule in direction.get("rules", [])]

    config = styles()

    # A flat fill is the single clearest tell of a generated page, so the
    # recipes travel with every direction.
    recipes = {
        k: v for k, v in config.get("backdrop_recipes", {}).items()
        if not k.startswith("_")
    }
    if recipes:
        lines += ["", "BACKDROP — pick what suits the direction, never a flat fill:"]
        lines += [f"  {name}: {how}" for name, how in recipes.items()]

    # Glass only where the direction asks for it; applied everywhere it would
    # flatten the variety between trades back out again.
    wants_glass = "glass" in " ".join(direction.get("rules", [])).lower() or "glass" in key
    glass = config.get("glass_surface", {}).get("rules", [])
    if wants_glass and glass:
        lines += ["", "GLASS SURFACES — all of these, not a subset:"]
        lines += [f"  {rule}" for rule in glass]

    universal = config.get("universal_rules", [])
    if universal:
        lines += ["", "ALWAYS:"] + [f"  {rule}" for rule in universal]
    return "\n".join(lines)


def attribution_email() -> str:
    config = {**FALLBACK["attribution"], **defaults().get("attribution", {})}
    return config.get("email", "")
