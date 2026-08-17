"""Look at the photographs and put the best one first.

The crawler orders images by where it found them: og:image, then lazy-loaded
and srcset sources, then plain <img>. og:image leading is a good rule — it is
the business's own pick — but it is a rule about markup, not about pictures,
and the two come apart in ways only looking can catch.

Both failures are in the leads currently in the database. The Lab's og:image is
`Social_1200x.jpg`, a share card: the right file for a Facebook preview, and
usually type over a photo rather than a photograph. Café Calibre's harvest
carries `Ellipse.png` and `Arrow_-_Right_1.png` — interface decoration that
passes every URL test we have, since the noise pattern looks for logos and
icons and these declare no size for the 300px floor to catch.

A name pattern could be extended to cover ellipses and arrows, and would then
miss the next shape. Whether a file is a photograph of a business is a question
about the image, so it is asked of something that can see the image.

Two rules govern what comes back:

Indices, never URLs. The model is shown numbered pictures and returns numbers,
which are mapped back here. It is the same rule the harvest already follows —
"images and socials are gathered by the crawler and must never be
model-supplied" — and it means an invented or altered URL is not expressible.

Fail open, always. Ranking is an improvement on an order that already works. A
timeout, a merchant's server refusing Anthropic's fetch, a model that rejects
every photo — each returns the input untouched. A demo built in the crawler's
order is a fine demo; a demo that fails to build is not.
"""

import logging

from pydantic import BaseModel, Field

from loom.llm.client import Claude, Model

log = logging.getLogger(__name__)

# Every image is sent to be looked at, so the count is the cost. Twelve covers
# the hero and a gallery several times over; past that we are paying to rank
# pictures no page will show.
MAX_SEEN = 12

SYSTEM = """You are choosing photographs for a small business's website.

You will be shown numbered images from the business's existing site.

Return the indices of the ones that are PHOTOGRAPHS OF THE BUSINESS — its
premises, its interior, its food, drink or products, its staff at work.

Exclude anything that is not a photograph of the business:
- interface decoration: arrows, chevrons, ellipses, dividers, background shapes
- logos, wordmarks, badges, app-store buttons, payment-method marks
- share cards and banners that are mostly type set over an image
- maps, screenshots, illustrations, clip art
- stock photography that plainly is not this business

Order what remains best-first, judged as the single large image at the top of
the page:
1. the premises or interior, wide enough to read as a place
2. food, drink or product, close and well lit
3. people at work in the business
Within a tier prefer sharper, better lit, and less cluttered by text.

Return an empty list only if none of the images are photographs of the
business."""


class Ranked(BaseModel):
    keep: list[int] = Field(
        default_factory=list,
        description="Indices of photographs of the business, best hero first.",
    )
    why: str = Field(
        "",
        description="One short sentence on why the first index leads.",
    )


def _clean(indices: list[int], count: int) -> list[int]:
    """In-range, de-duplicated, order preserved."""
    seen: set[int] = set()
    out: list[int] = []
    for i in indices:
        if 0 <= i < count and i not in seen:
            seen.add(i)
            out.append(i)
    return out


async def rank(
    urls: list[str], *, business: str = "", claude: Claude | None = None
) -> list[str]:
    """The photographs, best hero first. Returns `urls` unchanged on any doubt."""
    if len(urls) < 2:
        return urls

    looked_at = urls[:MAX_SEEN]
    tail = urls[MAX_SEEN:]

    content: list[dict] = []
    for index, url in enumerate(looked_at):
        # The label precedes its picture so the model can refer to one
        # unambiguously; without it a list of images has no names in it.
        content.append({"type": "text", "text": f"Image {index}:"})
        content.append({"type": "image", "source": {"type": "url", "url": url}})
    content.append(
        {
            "type": "text",
            "text": (
                f"The business is {business or 'a small local business'}. "
                "Which of these are photographs of it, and in what order?"
            ),
        }
    )

    claude = claude or Claude.tracked("image_pick")
    try:
        result = await claude.extract_model(
            content, Ranked, model=Model.SONNET, system=SYSTEM
        )
    except Exception as e:
        # Most often a merchant's server refusing the fetch, which is their
        # configuration and not a fault here. Logged, not raised.
        log.info("image ranking unavailable (%s) — keeping crawl order", e)
        return urls

    keep = _clean(result.keep, len(looked_at))
    if not keep:
        # Every image rejected. Occasionally true, but a site whose photographs
        # are all interface decoration is rarer than a bad answer, and the cost
        # of believing it is a demo with no pictures at all.
        log.info("image ranking kept nothing — keeping crawl order")
        return urls

    ordered = [looked_at[i] for i in keep]
    # Anything past MAX_SEEN was never looked at, so it is neither promoted nor
    # thrown away — it keeps its place behind everything that was judged.
    return ordered + tail
