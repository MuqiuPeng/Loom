"""What to search for, as a curated list rather than whatever comes to mind.

A free-text query box quietly narrows the whole pipeline: you type "cafe",
because cafés are what a scouting tool makes you think of, and never find the
plumber with no website and a four-figure average job. The list lives in
config/scout_industries.json — see its `_comment` for the reasoning.

One industry expands to several provider queries, because providers match on
their own category vocabulary: "plumber" and "plumbing service" return
different sets from the same index. Results are merged on place_id, so a
business that answers to two of them appears once.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

CONFIG_PATH = Path("config/scout_industries.json")


class Industry(BaseModel):
    key: str
    label: str
    queries: list[str] = Field(default_factory=list)
    visitor_led: bool = False
    why: str = ""


@lru_cache(maxsize=1)
def _load(mtime: float) -> list[Industry]:
    try:
        raw: dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [Industry(**entry) for entry in raw.get("industries", [])]


def industries() -> list[Industry]:
    try:
        return _load(CONFIG_PATH.stat().st_mtime)
    except OSError:
        return []


def by_key(key: str) -> Industry | None:
    return next((i for i in industries() if i.key == key), None)


def queries_for(keys: list[str]) -> list[str]:
    """Every provider query these industries expand to, in order, deduped.

    An unknown key is passed through as a literal query. That keeps the free
    text box working: whatever you type that isn't an industry key is simply
    the search term it always was.
    """
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        industry = by_key(key)
        terms = industry.queries if industry else [key]
        for term in terms:
            lowered = term.lower()
            if lowered not in seen:
                seen.add(lowered)
                out.append(term)
    return out
