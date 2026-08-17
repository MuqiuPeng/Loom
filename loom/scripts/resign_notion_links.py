"""Re-sign the resume PDF links already published to the Notion job tracker.

A signed link embeds an HMAC of the artifact id, so rotating the signing
secret invalidates every link that has ever been written into a Notion row.
The rows themselves are still correct — only the `sig` query parameter is
stale — so this walks the tracker and rewrites that one parameter.

Run it after changing LOOM_SIGNING_SECRET:

    python -m loom.scripts.resign_notion_links --dry-run
    python -m loom.scripts.resign_notion_links

Idempotent: a link that already carries a valid signature is left alone.
"""

import argparse
import asyncio
import os
import re
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx
from dotenv import load_dotenv

load_dotenv()

from loom.services.job_watcher import NOTION_API, _headers, _row_fields  # noqa: E402
from loom.services.signing import resume_pdf_sig  # noqa: E402

_PDF_PATH = re.compile(r"^/api/resumes/([0-9a-fA-F-]{36})/pdf$")


def _resigned(url: str) -> tuple[str, str] | None:
    """(artifact_id, corrected_url) for a resume-PDF link, else None."""
    parts = urlparse(url)
    match = _PDF_PATH.match(parts.path)
    if not match:
        return None
    artifact_id = match.group(1)
    current = (parse_qs(parts.query).get("sig") or [""])[0]
    wanted = resume_pdf_sig(artifact_id)
    if current == wanted:
        return None  # already valid
    return artifact_id, urlunparse(parts._replace(query=f"sig={wanted}"))


async def _all_rows(client: httpx.AsyncClient) -> list[dict]:
    db_id = os.environ["NOTION_JOBS_DB_ID"]
    rows, cursor = [], None
    while True:
        payload: dict = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        r = await client.post(f"{NOTION_API}/databases/{db_id}/query", json=payload)
        r.raise_for_status()
        body = r.json()
        rows += body.get("results", [])
        cursor = body.get("next_cursor")
        if not body.get("has_more"):
            return rows


async def main(dry_run: bool) -> None:
    if not (os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_JOBS_DB_ID")):
        raise SystemExit("NOTION_TOKEN / NOTION_JOBS_DB_ID not set")

    async with httpx.AsyncClient(headers=_headers(), timeout=30) as client:
        rows = await _all_rows(client)
        print(f"{len(rows)} rows in the tracker")

        stale = []
        for row in rows:
            url = _row_fields(row).get("resume_url")
            if not url:
                continue
            fixed = _resigned(url)
            if fixed:
                stale.append((row["id"], _row_fields(row)["title"], fixed[1]))

        print(f"{len(stale)} link(s) need re-signing")
        if dry_run:
            for _, title, _url in stale:
                print(f"  would re-sign: {title}")
            return

        ok = failed = 0
        for page_id, title, new_url in stale:
            r = await client.patch(
                f"{NOTION_API}/pages/{page_id}",
                json={"properties": {"简历": {"url": new_url}}},
            )
            if r.status_code == 200:
                ok += 1
                print(f"  re-signed: {title}")
            else:
                failed += 1
                print(f"  FAILED   : {title} — {r.status_code} {r.text[:120]}")
        print(f"\nre-signed {ok}, failed {failed}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.dry_run))
