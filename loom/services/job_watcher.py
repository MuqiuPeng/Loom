"""Job tracker watcher — daily automated resume generation from Notion.

Reads the Notion "LinkedIn Job Tracker" database, fetches each job's JD
(LinkedIn guest endpoint, falling back to the row's own 匹配理由/潜在风险
summary), runs the resume pipeline, and writes the signed PDF link back
to the row's 简历 property.

Runs daily at 10:00 Australia/Sydney via an in-process scheduler, and on
demand via POST /api/tasks/process-job-tracker.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx

from loom.current_user import get_current_user

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
SYDNEY = ZoneInfo("Australia/Sydney")
RUN_AT_HOUR = 10

# Only generate for actionable rows; cap per run to bound Claude spend.
# 待看 is what the daily digest task writes on intake, so that is the queue.
PENDING_STATUS = "待看"
ACTIONABLE_STATUSES = {PENDING_STATUS}
DONE_STATUS = "待投递"
# Ceiling per run — a runaway guard, not a throttle. Must stay comfortably
# above the daily intake or the queue never drains. At ~$0.34 and ~6 min per
# resume, a full run of 25 costs ~$8.4 and ~2.5h in the background.
MAX_JOBS_PER_RUN = 25

_run_lock = asyncio.Lock()

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _enabled() -> bool:
    return bool(os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_JOBS_DB_ID"))


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '')}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ── Notion row helpers ───────────────────────────────────────────────

def _plain(prop: dict, kind: str) -> str:
    items = prop.get(kind) or []
    return "".join(x.get("plain_text", "") for x in items)


def _row_fields(row: dict) -> dict[str, Any]:
    p = row["properties"]
    return {
        "page_id": row["id"],
        "title": _plain(p.get("职位", {}), "title"),
        "company": _plain(p.get("公司", {}), "rich_text"),
        "location": _plain(p.get("地点", {}), "rich_text"),
        "salary": _plain(p.get("薪资", {}), "rich_text"),
        "url": (p.get("链接", {}) or {}).get("url"),
        "jd_source": (p.get("JD来源", {}) or {}).get("url"),
        "status": ((p.get("状态", {}) or {}).get("select") or {}).get("name"),
        "match_reason": _plain(p.get("匹配理由", {}), "rich_text"),
        "risk": _plain(p.get("潜在风险", {}), "rich_text"),
        "resume_url": (p.get("简历", {}) or {}).get("url"),
    }


async def _query_pending(client: httpx.AsyncClient) -> list[dict]:
    db_id = os.environ["NOTION_JOBS_DB_ID"]
    rows, cursor = [], None
    while True:
        payload: dict = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        r = await client.post(f"{NOTION_API}/databases/{db_id}/query", json=payload)
        r.raise_for_status()
        data = r.json()
        rows += data["results"]
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]

    pending = []
    for row in rows:
        f = _row_fields(row)
        if f["resume_url"]:
            continue
        if f["status"] not in ACTIONABLE_STATUSES:
            continue
        if not f["title"]:
            continue
        pending.append(f)
    return pending


def _rt(text: str) -> dict:
    """Notion rich_text property value."""
    return {"rich_text": [{"type": "text", "text": {"content": (text or "")[:1900]}}]}


async def _find_row_by_url(url: str) -> dict | None:
    """Return {"page_id", "url", "title", "status"} for an existing row with this 链接."""
    async with httpx.AsyncClient(headers=_headers(), timeout=30.0) as client:
        r = await client.post(
            f"{NOTION_API}/databases/{os.environ['NOTION_JOBS_DB_ID']}/query",
            json={"filter": {"property": "链接", "url": {"equals": url}}, "page_size": 1},
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        row = results[0]
        f = _row_fields(row)
        # Key is row_status, not status — callers merge this into a response
        # envelope that owns the "status" key.
        return {"page_id": row["id"], "url": row.get("url"),
                "title": f["title"], "row_status": f["status"]}


async def create_tracker_row(fields: dict) -> dict:
    """Create a job row in the Notion tracker with 状态=待生成.

    fields: title (required), company, location, salary, url, jd_source,
            match_score, match_reason, risk, note
    Returns {"page_id", "url", "title"}.
    """
    if not _enabled():
        raise RuntimeError("Job tracker not configured: set NOTION_TOKEN and NOTION_JOBS_DB_ID")
    title = (fields.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")

    # Dedup: same job URL already tracked → return the existing row
    if fields.get("url"):
        existing = await _find_row_by_url(fields["url"])
        if existing:
            return {**existing, "duplicate": True}

    props: dict = {
        "职位": {"title": [{"type": "text", "text": {"content": title[:200]}}]},
        "状态": {"select": {"name": PENDING_STATUS}},
        "发现日期": {"date": {"start": datetime.now(SYDNEY).date().isoformat()}},
    }
    for key, prop in (("company", "公司"), ("location", "地点"),
                      ("salary", "薪资"), ("match_reason", "匹配理由"),
                      ("risk", "潜在风险"), ("note", "备注")):
        if fields.get(key):
            props[prop] = _rt(fields[key])
    for key, prop in (("url", "链接"), ("jd_source", "JD来源")):
        if fields.get(key):
            props[prop] = {"url": fields[key]}
    if fields.get("match_score") is not None:
        try:
            props["匹配分"] = {"number": float(fields["match_score"])}
        except (TypeError, ValueError):
            pass

    async with httpx.AsyncClient(headers=_headers(), timeout=30.0) as client:
        r = await client.post(f"{NOTION_API}/pages", json={
            "parent": {"database_id": os.environ["NOTION_JOBS_DB_ID"]},
            "properties": props,
        })
        if r.status_code != 200:
            raise RuntimeError(f"Notion row create failed: {r.text[:300]}")
        page = r.json()

    logger.info("job-tracker: created row for %s", title)
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info("user_action", "job_tracker.add", f"Added job to tracker: {title}")
    except Exception:
        pass
    return {"page_id": page["id"], "url": page.get("url"), "title": title}


async def _write_back_success(client: httpx.AsyncClient, page_id: str,
                              resume_url: str) -> None:
    """Success: set the resume link and flip 状态 → 待投递. No note."""
    props = {
        "简历": {"url": resume_url},
        "状态": {"select": {"name": DONE_STATUS}},
    }
    r = await client.patch(f"{NOTION_API}/pages/{page_id}", json={"properties": props})
    if r.status_code != 200:
        logger.warning("Notion write-back failed for %s: %s", page_id, r.text[:200])


async def _write_back_failure(client: httpx.AsyncClient, page_id: str, note: str) -> None:
    """Failure: record the error in 简历备注; 状态 stays 待生成 for retry."""
    props = {
        "简历备注": {"rich_text": [{"type": "text", "text": {"content": note[:1900]}}]},
    }
    r = await client.patch(f"{NOTION_API}/pages/{page_id}", json={"properties": props})
    if r.status_code != 200:
        logger.warning("Notion write-back failed for %s: %s", page_id, r.text[:200])


# ── JD fetching ──────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}|[ \t]{2,}")


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", html, flags=re.I)
    text = _TAG_RE.sub(" ", html)
    import html as html_mod
    text = html_mod.unescape(text)
    return _WS_RE.sub("\n", text).strip()


async def _fetch_jd_text(fields: dict) -> tuple[str, str]:
    """Return (jd_text, source). Tries LinkedIn guest endpoint, then the
    JD来源 URL, then falls back to the row's own summary fields."""
    urls = []
    url = fields.get("url") or ""
    m = re.search(r"linkedin\.com/jobs/view/(\d+)", url)
    if m:
        urls.append((f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}", "linkedin-guest"))
    if fields.get("jd_source") and fields["jd_source"] != url:
        urls.append((fields["jd_source"], "jd-source"))
    if url and not m:
        urls.append((url, "link"))

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                 headers={"User-Agent": UA}) as client:
        for target, source in urls:
            try:
                r = await client.get(target)
                if r.status_code == 200 and len(r.text) > 500:
                    text = _strip_html(r.text)
                    if len(text) > 400:
                        return text[:20000], source
            except Exception as e:
                logger.info("JD fetch failed (%s): %s", source, e)

    # Fallback: the tracker row itself carries a JD digest
    parts = [
        f"Job Title: {fields['title']}",
        f"Company: {fields['company']}" if fields["company"] else "",
        f"Location: {fields['location']}" if fields["location"] else "",
        f"Salary: {fields['salary']}" if fields["salary"] else "",
        f"Match analysis (JD digest): {fields['match_reason']}" if fields["match_reason"] else "",
        f"Requirements / risks: {fields['risk']}" if fields["risk"] else "",
    ]
    return "\n".join(x for x in parts if x), "row-digest"


# ── Pipeline execution ───────────────────────────────────────────────

async def _run_pipeline_for_job(storage: Any, fields: dict, jd_text: str) -> tuple[str, str]:
    """Run analyze-jd + generate-resume synchronously. Returns (artifact_id, pdf_url)."""
    from loom.api import STATUS_PERCENT, _run_generate_resume  # noqa: F401
    from loom.services.signing import resume_pdf_url
    from loom.steps import ParseJDStep
    from loom.storage.resume import JDRecord
    from loom.triggers import ManualTrigger

    # Unattended: no request bound this, so it runs as LOOM_DEFAULT_USER_ID.
    owner = get_current_user()

    # 1. Parse JD → JDRecord
    trigger = ManualTrigger(user_id=owner)
    trigger.set_data({"jd_raw_text": jd_text})
    context = await trigger.emit()
    parse_step = ParseJDStep(storage=storage)
    context = await parse_step.run(context)
    parsed = context.data.get("jd_parsed", {})

    jd = JDRecord(
        user_id=owner,
        company=parsed.get("company") or fields["company"] or None,
        title=parsed.get("title") or fields["title"],
        raw_text=jd_text,
        required_skills=parsed.get("required_skills", []),
        preferred_skills=parsed.get("preferred_skills", []),
        key_requirements=parsed.get("key_requirements", []),
    )
    await storage.save_jd_record(jd)

    # 2. Generate resume via the existing background task logic (run inline)
    from loom.storage.resume import Task
    task = Task(type="generate_resume", status="pending",
                input_data={"jd_record_id": str(jd.id), "source": "job-watcher"},
                user_id=owner)
    await storage.save_task(task)
    await _run_generate_resume(task.id, str(jd.id), "en", "markdown", storage, owner)

    done = await storage.get_task(task.id, user_id=owner)
    if done.status != "completed":
        raise RuntimeError(f"generation failed: {done.error}")
    artifact_id = (done.output_data or {}).get("resume_artifact_id")
    if not artifact_id:
        raise RuntimeError("generation completed but no artifact id")
    return artifact_id, resume_pdf_url(artifact_id)


# ── Main run ─────────────────────────────────────────────────────────

async def process_job_tracker(storage: Any, limit: int = MAX_JOBS_PER_RUN) -> dict:
    """Process pending rows. Returns a summary dict."""
    if not _enabled():
        return {"status": "disabled", "detail": "NOTION_TOKEN / NOTION_JOBS_DB_ID not set"}

    if _run_lock.locked():
        return {"status": "busy", "detail": "a run is already in progress"}

    async with _run_lock:
        summary = {"processed": [], "failed": [], "skipped": 0}
        async with httpx.AsyncClient(headers=_headers(), timeout=30.0) as notion:
            pending = await _query_pending(notion)
            summary["pending_total"] = len(pending)
            if len(pending) > limit:
                summary["skipped"] = len(pending) - limit
                pending = pending[:limit]

            for fields in pending:
                name = f"{fields['title']} @ {fields['company']}"
                try:
                    jd_text, source = await _fetch_jd_text(fields)
                    artifact_id, pdf_url = await _run_pipeline_for_job(storage, fields, jd_text)
                    await _write_back_success(notion, fields["page_id"], pdf_url)
                    summary["processed"].append({"job": name, "artifact_id": artifact_id, "jd_source": source})
                    logger.info("job-watcher: generated resume for %s (%s)", name, source)
                except Exception as e:
                    logger.exception("job-watcher: failed for %s", name)
                    try:
                        now = datetime.now(SYDNEY).strftime("%Y-%m-%d %H:%M")
                        await _write_back_failure(notion, fields["page_id"], f"{now} 生成失败: {str(e)[:300]}")
                    except Exception:
                        pass
                    summary["failed"].append({"job": name, "error": str(e)[:200]})

        try:
            from loom.services.logger import logger as loom_logger
            await loom_logger.info(
                "system", "job_watcher.run",
                f"Job tracker run: {len(summary['processed'])} generated, "
                f"{len(summary['failed'])} failed, {summary['skipped']} deferred")
        except Exception:
            pass
        return summary


# ── Daily scheduler ──────────────────────────────────────────────────

def _seconds_until_next_run() -> float:
    now = datetime.now(SYDNEY)
    nxt = now.replace(hour=RUN_AT_HOUR, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


async def daily_scheduler_loop() -> None:
    """Sleep until 10:00 Sydney each day, then process the tracker."""
    if not _enabled():
        logger.info("job-watcher scheduler disabled (missing Notion config)")
        return
    logger.info("job-watcher scheduler started; next run in %.0f min",
                _seconds_until_next_run() / 60)
    while True:
        try:
            await asyncio.sleep(_seconds_until_next_run())
            from loom.api import get_storage
            summary = await process_job_tracker(get_storage())
            logger.info("job-watcher daily run: %s", summary)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("job-watcher daily run crashed; retrying tomorrow")
            await asyncio.sleep(60)
