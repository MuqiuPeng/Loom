"""One Notion client for the whole project.

Three modules each carried their own NOTION_API constant, version string and
header builder, and two of them hand-rolled pagination. None handled a 429.

That last one is not cosmetic. Notion allows roughly three requests a second.
Sending a batch of approved emails means one PATCH per row to record the
outcome, so a run of twenty will hit the limit — and a silently dropped PATCH
leaves a row still marked Approved after its email has gone out. The next poll
sends it again, to someone who has already been written to.

So requests retry with backoff, and honour Retry-After when Notion sends one.
"""

import asyncio
import os
import random

import httpx

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"

MAX_ATTEMPTS = 4
BASE_BACKOFF = 1.0
# Notion caps a single rich_text value at 2000 characters.
TEXT_LIMIT = 2000


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '')}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
    }


def token_present() -> bool:
    return bool(os.environ.get("NOTION_TOKEN"))


def rich(text: str) -> list[dict]:
    """A rich_text value, truncated to what Notion will accept."""
    return [{"type": "text", "text": {"content": (text or "")[:TEXT_LIMIT]}}]


def plain(row: dict, name: str) -> str:
    """Read a title or rich_text property back as a plain string."""
    prop = row.get("properties", {}).get(name) or {}
    parts = prop.get("rich_text") or prop.get("title") or []
    return "".join(p.get("plain_text", "") for p in parts)


class NotionError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Notion {status}: {body[:300]}")
        self.status = status


async def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    """One Notion call, retried on throttling and transient failures.

    Raises NotionError on a genuine rejection — a caller that ignores it would
    otherwise carry on as though a write had happened.
    """
    url = f"{API}{path}"
    last: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await client.request(method, url, json=json, params=params)
        except httpx.HTTPError as e:
            last = NotionError(0, str(e))
        else:
            if response.status_code < 300:
                return response.json()
            if response.status_code in (429, 500, 502, 503, 504):
                last = NotionError(response.status_code, response.text)
                # Notion tells us how long to wait when it throttles; guessing
                # shorter just burns another request against the same limit.
                after = response.headers.get("Retry-After")
                delay = (
                    float(after)
                    if after and after.replace(".", "", 1).isdigit()
                    else BASE_BACKOFF * (2**attempt) + random.uniform(0, 0.3)
                )
                if attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(delay)
                    continue
            else:
                raise NotionError(response.status_code, response.text)

    raise last or NotionError(0, "exhausted retries")


async def paginate(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Every result across pages, rather than the first hundred.

    Notion returns 100 at a time and a cursor; forgetting the cursor is how a
    query quietly reports fewer rows than exist, which reads as data loss.
    """
    results: list[dict] = []
    cursor: str | None = None

    while True:
        body = dict(json or {})
        query = dict(params or {})
        if cursor:
            # GET endpoints take the cursor as a query param, POST in the body.
            if method.upper() == "GET":
                query["start_cursor"] = cursor
            else:
                body["start_cursor"] = cursor

        page = await request(
            client, method, path,
            json=body if method.upper() != "GET" else None,
            params=query or None,
        )
        results.extend(page.get("results", []))

        if limit and len(results) >= limit:
            return results[:limit]
        if not page.get("has_more"):
            return results
        cursor = page.get("next_cursor")
        if not cursor:
            return results


def session(timeout: float = 20.0) -> httpx.AsyncClient:
    """An httpx client already carrying the Notion headers."""
    return httpx.AsyncClient(timeout=timeout, headers=headers())
