"""Build and publish a mock site for a business, to pitch with.

The demo is the pitch. Turning up with a working page built from a shop's own
menu beats any description of what you could do for them.

Layout on disk — one folder, one Vercel project, a path per business:

    output/loom-demos/
        index.html          listing of every demo built
        marrickville-coffee/index.html
        illi-hill/index.html

Deploying re-uploads the whole folder, so every demo keeps a stable URL and
you don't accumulate a Vercel project per shop.

Every generated page carries `noindex, nofollow`. These pages use a real
business's name and menu; they must never turn up in search results competing
with the business itself.
"""

import asyncio
import re
import secrets
import shutil
from pathlib import Path

from loom.llm.client import Claude, Model
from loom.services.site_harvest import Harvest

# The folder name becomes the Vercel project name on first deploy.
DEMO_ROOT = Path("output/loom-demos")

BUILD_SYSTEM = """You build a single-page website for a small local business.

Output ONLY the HTML document — no markdown fence, no commentary.

Requirements:
- One self-contained file: all CSS in a <style> tag, no external requests of
  any kind except <img> tags using the exact image URLs you are given.
- Include <meta name="robots" content="noindex, nofollow"> in the head.
- Include <meta name="viewport" content="width=device-width, initial-scale=1">.
- Mobile first. It must look right on a phone — that is usually the thing
  wrong with their current site.
- Sections: hero with the business name, menu (grouped by section when the
  data has sections), hours, location and contact, footer.
- Use ONLY the facts provided. Never invent a menu item, a price, an address
  or an opening hour — the owner reads this page and spots a fabrication
  immediately. Where a section has no data, follow the placeholder
  instructions given below rather than filling it with plausible-looking
  content.
- Follow the ART DIRECTION block below to the letter. It is the brief, not a
  suggestion — the point of this page is that it looks designed rather than
  generated, and a business owner recognises the difference immediately.
- No stock-template look, no lorem ipsum, no placeholder images.
- If image URLs are supplied, use them; otherwise use CSS colour and type to
  carry the design."""


_DOC_START_RE = re.compile(r"<!doctype\s+html|<html\b", re.I)


def extract_document(text: str) -> str:
    """Pull the HTML document out of whatever the model returned.

    Stripping a ``` fence is not enough: a repair round in particular likes to
    open with a sentence — "Here's the corrected HTML with..." — which then
    renders as English prose across the top of a page shown to a client. Cut
    to the first doctype or <html> instead of trusting the model to comply.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    match = _DOC_START_RE.search(text)
    if match:
        text = text[match.start():]
    # Anything after the closing tag is commentary too.
    end = text.lower().rfind("</html>")
    if end != -1:
        text = text[: end + len("</html>")]
    return text.strip()


def new_slug() -> str:
    """An opaque public URL for one demo. Names nothing and derives from nothing.

    The slug used to be the business name plus the tail of its Google place_id
    plus a fingerprint of the owner. Readable, and wrong twice over.

    It named the shop. The demo carries that shop's real name, address, phone
    and trading hours, and it answers to anyone who has the link; a URL reading
    `/demo/caf-calibre-…` makes an unsent mockup look like the business's own
    site to whoever it reaches. noindex keeps it out of search results, which
    is not the same as keeping the shop's name out of the address bar.

    Worse, it was derivable. The name is public and the place_id is public —
    anyone can read both off Google Maps — so the only part not sitting in
    plain sight was a four-character hash of the user, and four characters is
    sixty-five thousand guesses. The address of a page about a named business
    should not be computable by anyone who knows the business.

    So: random, and nothing else. Determinism is not lost with it — the slug is
    stored on the lead and read back before this is ever called, which is what
    actually keeps a shared link working across rebuilds. The uniqueness the
    old formula worked for is now sixty-four bits of entropy, with the partial
    unique index on demo_slug as the backstop that fails a write rather than
    letting a read land on somebody else's page.
    """
    return secrets.token_hex(8)


def _facts(lead: dict, harvest: Harvest) -> str:
    """Assemble the brief, honouring whatever the user ticked in the panel."""
    pick = harvest.selection
    images = pick.images_from(harvest.images)
    menu = pick.menu_from(harvest.menu)

    lines = [f"Business name: {lead.get('google_name') or lead.get('site_title') or 'Unknown'}"]
    if pick.highlight:
        lines.append(f"Lead the page on this: {pick.highlight}")
    if harvest.about and pick.use_about:
        lines.append(f"About: {harvest.about}")
    # Address and phone come from the harvest only. Falling back to Google's
    # copy would republish Places Content on a public page, which the Maps
    # Platform terms don't allow — better an omitted contact block than that.
    if harvest.address:
        lines.append(f"Address: {harvest.address}")
    if harvest.phone:
        lines.append(f"Phone: {harvest.phone}")
    if harvest.hours and pick.use_hours:
        lines.append(f"Hours: {harvest.hours}")
    if harvest.socials:
        lines.append(
            "Socials: "
            + ", ".join(f"{k}: {v}" for k, v in harvest.socials.items())
        )
    if images:
        lines.append("Image URLs (use these exact URLs):")
        lines += [f"  {u}" for u in images[:8]]
    if menu:
        lines.append("Menu:")
        for item in menu:
            bits = [item.name]
            if item.price:
                bits.append(item.price)
            if item.section:
                bits.append(f"[{item.section}]")
            if item.description:
                bits.append(f"— {item.description}")
            lines.append("  " + " ".join(bits))
    else:
        lines.append("Menu: none found — omit the menu section entirely.")
    return "\n".join(lines)


async def build_html(
    lead: dict,
    harvest: Harvest,
    *,
    claude: Claude | None = None,
    style: str | None = None,
) -> str:
    """Generate the demo page for one business."""
    from loom.services.demo_defaults import art_direction, guidance

    claude = claude or Claude.tracked("demo_build")
    kind = lead.get("primary_type")
    html = await claude.complete(
        f"Build the site from these facts:\n\n{_facts(lead, harvest)}\n"
        + art_direction(kind, style)
        + guidance(harvest, kind),
        model=Model.SONNET,
        system=BUILD_SYSTEM,
        max_tokens=16000,
    )
    return extract_document(html)


def write_demo(slug: str, html: str) -> Path:
    """Write one demo into the deploy folder. Returns the file path."""
    folder = DEMO_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "index.html"
    path.write_text(html, encoding="utf-8")
    _write_index()
    return path


def _write_index() -> None:
    """A plain listing at the root so the deploy has an entry point."""
    demos = sorted(p.parent.name for p in DEMO_ROOT.glob("*/index.html"))
    links = "\n".join(f'<li><a href="/{d}/">{d}</a></li>' for d in demos)
    (DEMO_ROOT / "index.html").write_text(
        "<!doctype html><meta charset=utf-8>"
        '<meta name="robots" content="noindex, nofollow">'
        "<title>Loom demos</title>"
        "<style>body{font:16px/1.6 system-ui;margin:3rem auto;max-width:40rem}</style>"
        f"<h1>Demos</h1><ul>{links}</ul>",
        encoding="utf-8",
    )


def remove_demo(slug: str) -> None:
    shutil.rmtree(DEMO_ROOT / slug, ignore_errors=True)
    _write_index()


async def deploy() -> str:
    """Publish the whole demo folder to Vercel. Returns the deployment URL.

    Uses the Vercel CLI's existing login. One project, so URLs stay stable
    across redeploys; `--prod` means each business's path keeps working.
    """
    DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    _write_index()
    # No --name: the CLI dropped it. --yes links (creating on first run) a
    # project named after the folder, and writes the link into
    # output/loom-demos/.vercel so later deploys reuse the same project and
    # therefore the same URLs.
    process = await asyncio.create_subprocess_exec(
        "vercel", "deploy", str(DEMO_ROOT), "--prod", "--yes",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    out = stdout.decode().strip()
    if process.returncode != 0:
        raise RuntimeError(f"vercel deploy failed: {stderr.decode()[:400]}")
    # The CLI prints the deployment URL on the last line of stdout.
    url = out.splitlines()[-1].strip() if out else ""
    if not url.startswith("http"):
        raise RuntimeError(f"could not read a URL from vercel output: {out[:200]}")
    return url
