"""Find the menu when it is a file rather than a page, and read it.

Café Calibre's navigation has a "Menu" link like any café's. It points at
new_manu_all_items.pdf on Shopify's CDN — 109KB, application/pdf. The crawler
correctly declined to follow it, because it is not a page, and the harvest
came back with menu=0 for a business whose menu is one click from its home
page.

This is ordinary for small hospitality. A menu changes weekly, the person who
changes it has a PDF, and putting the PDF up is the shortest path. It is also
a real problem for them, which is why site_audit flags it separately: a
customer on a phone gets a pinch-to-zoom document, and Google gets nothing at
all to rank — nobody searching for a flat white in Dulwich Hill will ever find
that page through its menu.

FINDING IT. On the link text first, the address second. The address here reads
"new_manu_all_items" — the owner's typo, and a reminder that a filename is
whatever somebody typed. The anchor text is the reliable signal, because it is
the word the visitor is meant to click.

READING IT. The model reads the document directly; there is no PDF library
here and no OCR. Only when the pages produced no menu — a site that lists its
menu in HTML and also links a printable PDF should not be read twice, and the
HTML version is the better source anyway.

The same schema as the crawl path, so a menu that arrives this way is
indistinguishable downstream from one read off a page, and the rule that
governs it is the same one: never invent an item or a price. The document is
either legible or it is not.
"""

import base64
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

log = logging.getLogger(__name__)

# What a menu link says, on the anchor or in the address. Narrow on purpose:
# the crawler's page hints include "order" and "coffee", which on a shop site
# match half the catalogue.
_MENU_WORD = re.compile(r"\bmenus?\b|\bmanus?\b|carte|drinks?[\s_-]?list", re.I)

_LINK_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_TAGS_RE = re.compile(r"<[^>]+>")

# Formats the model can be handed directly. A .docx menu exists in the world
# and is not worth the dependency.
_READABLE = re.compile(r"\.(pdf|jpe?g|png|webp)(\?|$)", re.I)

# Big enough for a long wine list, small enough that a scanned brochure does
# not become the largest request this system makes.
MAX_BYTES = 12 * 1024 * 1024
FETCH_TIMEOUT = 20.0


def find(html: str, base: str) -> list[str]:
    """URLs of documents on this page that look like the menu, best first."""
    found: list[str] = []
    for href, inner in _LINK_RE.findall(html):
        url = urljoin(base, href.strip())
        if not url.startswith(("http://", "https://")) or not _READABLE.search(url):
            continue
        text = _TAGS_RE.sub(" ", inner)
        # Anchor text leads: it is what the visitor is told they are clicking,
        # and it survives whatever the file happens to be called.
        if _MENU_WORD.search(text) or _MENU_WORD.search(urlparse(url).path):
            if url not in found:
                found.append(url)
    return found


def _block(data: bytes, content_type: str) -> dict | None:
    """One document or image content block, or None if it cannot be sent."""
    kind = (content_type or "").split(";")[0].strip().lower()
    encoded = base64.standard_b64encode(data).decode()
    if kind == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": kind, "data": encoded},
        }
    if kind in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": kind, "data": encoded},
        }
    return None


async def read(url: str, *, claude=None) -> list:
    """The menu items in the document at `url`. Empty on any difficulty."""
    from loom.llm.client import Claude, Model
    from loom.services.site_harvest import EXTRACT_SYSTEM, Extracted

    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(url)
        if response.status_code >= 400 or len(response.content) > MAX_BYTES:
            return []
        block = _block(response.content, response.headers.get("content-type", ""))
    except Exception as e:
        log.info("could not fetch menu document %s (%s)", url, str(e)[:120])
        return []

    if block is None:
        return []

    claude = claude or Claude.tracked("menu_doc")
    try:
        data = await claude.extract_model(
            [
                block,
                {
                    "type": "text",
                    "text": (
                        "This is a small business's menu. Read every item, its "
                        "price exactly as printed, and the heading it sits "
                        "under. Return nothing but what the document shows."
                    ),
                },
            ],
            Extracted,
            model=Model.SONNET,
            system=EXTRACT_SYSTEM,
        )
    except Exception as e:
        log.info("could not read menu document %s (%s)", url, str(e)[:120])
        return []

    return [item for item in data.menu if item.name]
