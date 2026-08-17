"""Build a demo by filling a template, not by asking for a whole document.

Every generated page was a fresh composition, which meant re-rolling on every
run the things that must never be wrong: the viewport tag, the noindex, the
`-webkit-` prefix, the absence of invented prices, the absence of a sentence
of commentary above the doctype. Each of those has actually gone wrong at
least once, and each fix was a prompt tweak that might or might not hold.

A template cannot forget them. The resume side of this project already renders
from Jinja rather than asking for a whole document; this brings demos into
line.

What's lost is per-run variety inside one direction — which is what the twelve
art directions are for, and a hand-tuned template is more distinctive than a
model's reading of a rule list anyway.

Directions without a template fall back to generation, so the two can be
compared on the same lead.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from loom.services.demo_defaults import (
    defaults,
    palette_for,
    stock_note,
)
from loom.services.site_harvest import Harvest

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "demos"

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    # StrictUndefined, not the default: a template asking for a field nobody
    # supplied should fail loudly here rather than render an empty gap into a
    # page shown to a business owner.
    undefined=StrictUndefined,
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def has_template(direction: str) -> bool:
    return (TEMPLATE_DIR / f"{direction}.html.j2").exists()


def available_templates() -> list[str]:
    return sorted(
        p.name.removesuffix(".html.j2")
        for p in TEMPLATE_DIR.glob("*.html.j2")
        if not p.name.startswith("_")
    )


def _grouped_menu(harvest: Harvest) -> list[tuple[str, list]]:
    """Menu items in their sections, in the order they were found."""
    items = harvest.selection.menu_from(harvest.menu)
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item.section or "", []).append(item)
    return list(groups.items())


def build_context(lead: dict, harvest: Harvest, *, stock_used: bool = False) -> dict[str, Any]:
    """Everything a template may reference. Facts only — nothing invented."""
    config = defaults()
    sections = config.get("sections", {})
    attribution = config.get("attribution", {})
    images = harvest.selection.images_from(harvest.images)
    menu = harvest.selection.menu_from(harvest.menu)

    def sample(key: str) -> str:
        rows = sections.get(key, {}).get("sample_rows", [])
        return rows[0] if rows else ""

    phone = harvest.phone or ""
    return {
        "business": lead.get("google_name") or lead.get("site_title") or "This business",
        "about": harvest.about if harvest.selection.use_about else "",
        "hours": harvest.hours if harvest.selection.use_hours else "",
        "address": harvest.address or "",
        "phone": phone,
        # tel: wants no spaces or punctuation.
        "phone_href": "".join(c for c in phone if c.isdigit() or c == "+"),
        "images": images,
        "menu": menu,
        "menu_groups": _grouped_menu(harvest),
        "menu_is_real": bool(menu),
        "socials": harvest.socials,
        "palette": palette_for(lead.get("primary_type")),
        "attribution": attribution,
        "stock_used": stock_used,
        "stock_note": stock_note(),
        "sample_note": config.get("placeholder_note", "Sample"),
        "hours_sample": sample("hours"),
        "location_sample": sample("location"),
        "menu_sample": sample("menu"),
    }


def render_demo(
    direction: str, lead: dict, harvest: Harvest, *, stock_used: bool = False
) -> str | None:
    """Render one direction, or None if it has no template."""
    try:
        template = _env.get_template(f"{direction}.html.j2")
    except TemplateNotFound:
        return None
    return template.render(**build_context(lead, harvest, stock_used=stock_used))
