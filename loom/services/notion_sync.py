"""Notion sync service — mirrors the Loom profile to a Notion page.

The mirror is a MACHINE-READABLE data dump, not a display page: the complete
profile (bilingual fields, star_data, raw_text, tech_stack, priorities,
confidence, entity ids and relations) is serialized as JSON into code blocks.
Consumers reconstruct it by concatenating the code blocks' plain text in order.

Strategy: keep a child page titled "Loom Profile" under NOTION_PARENT_PAGE_ID.
On sync, archive the previous child page and create a fresh one from the
current profile. Profile mutations schedule a debounced sync so bursts of
edits produce a single rebuild.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from loom.current_user import get_current_user

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
PAGE_TITLE = "Loom Profile"

_debounce_task: asyncio.Task | None = None


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '')}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _enabled() -> bool:
    return bool(os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_PARENT_PAGE_ID"))


# ── Markdown → Notion rich_text ──────────────────────────────────────

_MD_PATTERN = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def _rich(text: str) -> list[dict]:
    """Convert **bold** and `code` markdown to Notion rich_text segments."""
    segments = []
    for part in _MD_PATTERN.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            segments.append({
                "type": "text",
                "text": {"content": part[2:-2]},
                "annotations": {"bold": True},
            })
        elif part.startswith("`") and part.endswith("`"):
            segments.append({
                "type": "text",
                "text": {"content": part[1:-1]},
                "annotations": {"code": True},
            })
        else:
            # Strip stray italics markers; cap at Notion's 2000-char limit
            clean = part.replace("*", "")[:2000]
            segments.append({"type": "text", "text": {"content": clean}})
    return segments or [{"type": "text", "text": {"content": ""}}]


def _h2(text: str) -> dict:
    return {"heading_2": {"rich_text": _rich(text)}}


def _h3(text: str) -> dict:
    return {"heading_3": {"rich_text": _rich(text)}}


def _p(text: str) -> dict:
    return {"paragraph": {"rich_text": _rich(text)}}


def _caption(text: str) -> dict:
    return {"paragraph": {"rich_text": [{
        "type": "text",
        "text": {"content": text[:2000]},
        "annotations": {"italic": True, "color": "gray"},
    }]}}


def _bullet(text: str) -> dict:
    return {"bulleted_list_item": {"rich_text": _rich(text)}}


def _divider() -> dict:
    return {"divider": {}}


def _fmt_date(d: str | None) -> str:
    if not d:
        return "Present"
    return str(d)[:7]


# ── Profile → JSON payload ───────────────────────────────────────────

async def _build_payload(storage: Any) -> dict:
    """Assemble the COMPLETE profile as a JSON-serializable dict.

    Every field of every entity is included (en/zh variants, star_data,
    raw_text, tech_stack, priority, confidence, ids, relations, dates) —
    downstream automation depends on this being lossless.
    """
    profile = await storage.get_profile(get_current_user())
    if not profile:
        return {"error": "no profile found"}

    experiences = []
    for exp in await storage.get_experiences(profile.id):
        e = exp.model_dump(mode="json")
        e["bullets"] = [b.model_dump(mode="json") for b in await storage.get_bullets(exp.id)]
        experiences.append(e)

    return {
        "source": "loom",
        "schema": "loom-profile-mirror/v1",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile.model_dump(mode="json"),
        "experiences": experiences,
        # All projects, standalone and experience-linked alike; the
        # experience_id field carries the relation.
        "projects": [p.model_dump(mode="json") for p in await storage.get_projects(profile.id)],
        "skills": [s.model_dump(mode="json") for s in await storage.get_skills(profile.id)],
        "education": [e.model_dump(mode="json") for e in await storage.get_education(profile.id)],
    }


def _json_code_blocks(payload: dict) -> list[dict]:
    """Serialize payload into Notion code blocks.

    Notion limits: 2000 chars per rich_text segment, 100 segments per block.
    Consumers concatenate all code-block plain text in order and json.loads it.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    segments = [text[i:i + 2000] for i in range(0, len(text), 2000)]
    blocks = []
    for i in range(0, len(segments), 100):
        rich = [{"type": "text", "text": {"content": s}} for s in segments[i:i + 100]]
        blocks.append({"code": {"rich_text": rich, "language": "json"}})
    return blocks


async def _build_blocks(storage: Any) -> list[dict]:
    payload = await _build_payload(storage)
    counts = (
        f"{len(payload.get('experiences', []))} experiences, "
        f"{len(payload.get('projects', []))} projects, "
        f"{len(payload.get('skills', []))} skills, "
        f"{len(payload.get('education', []))} education"
    )
    header = [
        _caption(
            "Machine-readable Loom profile mirror — auto-generated, do not edit. "
            f"Synced {payload.get('synced_at', '')} | {counts}. "
            "To consume: concatenate all JSON code blocks below in order, then parse."
        ),
    ]
    return header + _json_code_blocks(payload)


# ── Notion API operations ────────────────────────────────────────────

async def _archive_old_pages(client: httpx.AsyncClient, parent_id: str) -> None:
    cursor = None
    child_page_ids = []
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        r = await client.get(f"{NOTION_API}/blocks/{parent_id}/children", params=params)
        r.raise_for_status()
        data = r.json()
        for block in data.get("results", []):
            if block.get("type") == "child_page" and \
               block["child_page"].get("title") == PAGE_TITLE:
                child_page_ids.append(block["id"])
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    for pid in child_page_ids:
        r = await client.patch(f"{NOTION_API}/pages/{pid}", json={"archived": True})
        if r.status_code != 200:
            logger.warning("Failed to archive old Notion page %s: %s", pid, r.text[:200])


async def sync_profile_to_notion(storage: Any) -> str | None:
    """Rebuild the Notion profile page. Returns the new page URL, or None."""
    if not _enabled():
        logger.info("Notion sync skipped: NOTION_TOKEN / NOTION_PARENT_PAGE_ID not set")
        return None

    parent_id = os.environ["NOTION_PARENT_PAGE_ID"]
    blocks = await _build_blocks(storage)

    async with httpx.AsyncClient(headers=_headers(), timeout=30.0) as client:
        await _archive_old_pages(client, parent_id)

        r = await client.post(f"{NOTION_API}/pages", json={
            "parent": {"page_id": parent_id},
            "icon": {"type": "emoji", "emoji": "🧵"},
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": PAGE_TITLE}}]},
            },
            "children": blocks[:100],
        })
        r.raise_for_status()
        page = r.json()
        page_id = page["id"]

        # Append remaining blocks in batches of 100
        rest = blocks[100:]
        for i in range(0, len(rest), 100):
            r = await client.patch(
                f"{NOTION_API}/blocks/{page_id}/children",
                json={"children": rest[i:i + 100]},
            )
            r.raise_for_status()

    url = page.get("url")
    logger.info("Notion sync complete: %d blocks → %s", len(blocks), url)
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info("system", "notion.sync", f"Profile synced to Notion ({len(blocks)} blocks)")
    except Exception:
        pass
    return url


# ── Debounced scheduling (called from mutation middleware) ───────────

def schedule_sync(delay: float = 8.0) -> None:
    """Schedule a debounced profile sync; bursts of edits collapse into one."""
    if not _enabled():
        return
    global _debounce_task
    if _debounce_task and not _debounce_task.done():
        _debounce_task.cancel()

    async def _run() -> None:
        try:
            await asyncio.sleep(delay)
            from loom.api import get_storage
            await sync_profile_to_notion(get_storage())
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Notion sync failed")

    _debounce_task = asyncio.create_task(_run())
