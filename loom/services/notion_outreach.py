"""Put drafted emails in a Notion table and wait to be told to send them.

The approval lives outside this codebase on purpose. These are commercial
messages to real strangers, so the thing that decides "send this one" should
be a person looking at the actual words, on a phone, away from the machine
that wrote them.

Notion's button block can set a property but cannot call a webhook on every
plan, so the contract is deliberately dumb: the button flips Status to
"Approved", and Loom polls for that. Nothing here can send; sending lives in
mailer.py and only ever acts on rows already marked approved.

Set NOTION_OUTREACH_DB_ID once created, or let ensure_database() make it under
NOTION_PARENT_PAGE_ID.
"""

import os
from typing import Any

import httpx

from loom.services.notion import (
    TEXT_LIMIT,
    NotionError,
    paginate,
    request,
    rich,
    session,
    token_present,
)

STATUS_DRAFT = "Draft"
STATUS_APPROVED = "Approved"
STATUS_SENT = "Sent"
STATUS_FAILED = "Failed"
STATUS_CANCELLED = "Cancelled"
STATUS_REPLIED = "Replied"
STATUS_OPTED_OUT = "Opted out"


def enabled() -> bool:
    return token_present() and bool(
        os.environ.get("NOTION_OUTREACH_DB_ID") or os.environ.get("NOTION_PARENT_PAGE_ID")
    )


SCHEMA: dict[str, Any] = {
    "Business": {"title": {}},
    "Status": {
        "select": {
            "options": [
                {"name": STATUS_DRAFT, "color": "gray"},
                {"name": STATUS_APPROVED, "color": "green"},
                {"name": STATUS_SENT, "color": "blue"},
                {"name": STATUS_FAILED, "color": "red"},
                {"name": STATUS_CANCELLED, "color": "default"},
                {"name": STATUS_REPLIED, "color": "purple"},
                {"name": STATUS_OPTED_OUT, "color": "orange"},
            ]
        }
    },
    "To": {"email": {}},
    "Subject": {"rich_text": {}},
    "Body": {"rich_text": {}},
    "Demo": {"url": {}},
    "Template": {"rich_text": {}},
    "Lead": {"rich_text": {}},
    "Sent at": {"date": {}},
    "Error": {"rich_text": {}},
    # What came back. Kept on the same row rather than in a second table:
    # this is already one row per business, and the question being asked of
    # it — "did this one answer, and what did they say" — is answered badly
    # by two places to look.
    "Reply": {"rich_text": {}},
    "Replied at": {"date": {}},
    # The Message-ID of what we sent, so a reply can be matched by thread
    # rather than only by sender address.
    "Message ID": {"rich_text": {}},
}


_schema_checked: set[str] = set()


async def _add_missing_properties(client: httpx.AsyncClient, database_id: str) -> None:
    """Bring an existing table up to the current SCHEMA.

    ensure_database returns a configured table without looking at its columns,
    so every property added here after the table was first created would
    simply never exist on it — and a PATCH naming an unknown property fails,
    which would have made every reply silently fail to record on the one table
    that is actually in use.

    Notion merges properties on PATCH, so sending only the missing ones adds
    them without disturbing anything a person has since added by hand. Done
    once per process; the table does not change underneath us mid-run.
    """
    if database_id in _schema_checked:
        return
    _schema_checked.add(database_id)
    try:
        current = await request(client, "GET", f"/databases/{database_id}")
    except NotionError:
        return

    properties = current.get("properties", {})
    have = set(properties)
    missing = {name: spec for name, spec in SCHEMA.items() if name not in have}
    # The title property is created with the table and can't be re-added.
    missing.pop("Business", None)

    # Adding a property brings its options with it, but an existing Status
    # column keeps whatever options it already had — so "Replied" and "Opted
    # out" would be absent on the table already in use. Resend the whole
    # option list; Notion merges by name, so nothing added by hand is lost.
    existing_options = {
        option.get("name")
        for option in (properties.get("Status", {}).get("select", {}).get("options", []))
    }
    wanted_options = {
        option["name"] for option in SCHEMA["Status"]["select"]["options"]
    }
    if "Status" in have and wanted_options - existing_options:
        merged = [
            *(properties["Status"]["select"]["options"]),
            *(
                option
                for option in SCHEMA["Status"]["select"]["options"]
                if option["name"] not in existing_options
            ),
        ]
        missing["Status"] = {"select": {"options": merged}}

    if not missing:
        return
    try:
        await request(
            client, "PATCH", f"/databases/{database_id}",
            json={"properties": missing},
        )
    except NotionError:
        # Leave it; the caller's own write will fail loudly enough, and
        # guessing again on the next call achieves nothing.
        pass


async def ensure_database(client: httpx.AsyncClient) -> str | None:
    """Return the outreach database id, creating it if needed."""
    existing = os.environ.get("NOTION_OUTREACH_DB_ID")
    if existing:
        await _add_missing_properties(client, existing)
        return existing

    parent = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent:
        return None

    try:
        created = await request(
            client, "POST", "/databases",
            json={
                "parent": {"type": "page_id", "page_id": parent},
                "title": [{"type": "text", "text": {"content": "Loom Outreach"}}],
                "properties": SCHEMA,
            },
        )
    except NotionError:
        return None
    return created.get("id")


async def push_draft(lead: dict, draft: dict, demo_url: str = "") -> str | None:
    """Put one drafted email in the table as Draft. Returns the page id.

    Re-drafting the same lead updates its row rather than adding a second, so
    the table stays one line per business.
    """
    if not enabled():
        return None

    async with session() as client:
        database_id = await ensure_database(client)
        if not database_id:
            return None

        properties = {
            "Business": {"title": rich(lead.get("google_name") or lead.get("site_title") or "—")},
            "Status": {"select": {"name": STATUS_DRAFT}},
            "Subject": {"rich_text": rich(draft.get("subject", ""))},
            "Body": {"rich_text": rich(draft.get("body", ""))},
            "Template": {"rich_text": rich(draft.get("template", ""))},
            "Lead": {"rich_text": rich(lead.get("id", ""))},
        }
        if draft.get("to"):
            properties["To"] = {"email": draft["to"]}
        if demo_url:
            properties["Demo"] = {"url": demo_url}

        existing = await _find_by_lead(client, database_id, lead.get("id", ""))
        if existing:
            # Never reopen something already sent — that is how a second copy
            # reaches someone who already replied.
            if existing["status"] in (STATUS_SENT,):
                return existing["page_id"]
            await request(
                client, "PATCH", f"/pages/{existing['page_id']}",
                json={"properties": properties},
            )
            return existing["page_id"]

        try:
            created = await request(
                client, "POST", "/pages",
                json={"parent": {"database_id": database_id}, "properties": properties},
            )
        except NotionError:
            return None
        return created.get("id")


async def _find_by_lead(
    client: httpx.AsyncClient, database_id: str, lead_id: str
) -> dict | None:
    if not lead_id:
        return None
    try:
        found = await paginate(
            client, "POST", f"/databases/{database_id}/query",
            json={"filter": {"property": "Lead", "rich_text": {"equals": lead_id}}},
            limit=1,
        )
    except NotionError:
        return None
    if not found:
        return None
    row = found[0]
    return {"page_id": row["id"], "status": _status_of(row)}


def _status_of(row: dict) -> str:
    select = (row.get("properties", {}).get("Status") or {}).get("select") or {}
    return select.get("name", "")


def _plain(row: dict, name: str) -> str:
    from loom.services.notion import plain

    return plain(row, name)


async def approved_rows() -> list[dict]:
    """Rows a human has marked Approved and that have not been sent."""
    if not enabled():
        return []

    async with session() as client:
        database_id = await ensure_database(client)
        if not database_id:
            return []
        try:
            found = await paginate(
                client, "POST", f"/databases/{database_id}/query",
                json={"filter": {"property": "Status", "select": {"equals": STATUS_APPROVED}}},
                limit=50,
            )
        except NotionError:
            return []

        rows = []
        for row in found:
            to = (row.get("properties", {}).get("To") or {}).get("email")
            rows.append({
                "page_id": row["id"],
                "business": _plain(row, "Business"),
                "to": to,
                "subject": _plain(row, "Subject"),
                "body": _plain(row, "Body"),
                "lead_id": _plain(row, "Lead"),
            })
        return rows


async def sent_rows() -> list[dict]:
    """Rows already written to, so an inbound message can be matched to one.

    Includes Replied as well as Sent: a second message in the same thread has
    to land on the row too, and a business that says "actually yes" after
    saying "not right now" must not be invisible.
    """
    if not enabled():
        return []

    async with session() as client:
        database_id = await ensure_database(client)
        if not database_id:
            return []
        try:
            found = await paginate(
                client, "POST", f"/databases/{database_id}/query",
                json={
                    "filter": {
                        "or": [
                            {"property": "Status", "select": {"equals": s}}
                            for s in (STATUS_SENT, STATUS_REPLIED)
                        ]
                    }
                },
                limit=200,
            )
        except NotionError:
            return []

        rows = []
        for row in found:
            to = (row.get("properties", {}).get("To") or {}).get("email")
            rows.append({
                "page_id": row["id"],
                "business": _plain(row, "Business"),
                "to": (to or "").lower(),
                "lead_id": _plain(row, "Lead"),
                "message_id": _plain(row, "Message ID"),
                "status": _status_of(row),
            })
        return rows


async def record_reply(
    page_id: str,
    *,
    text: str,
    received_at: str = "",
    opted_out: bool = False,
    full_text: str = "",
) -> None:
    """Put an inbound message on the row it answers.

    An opt-out sets the status rather than only filling a column, because the
    status is what a person scanning the table on a phone actually reads, and
    what the send path checks.
    """
    if not enabled():
        return

    properties: dict[str, Any] = {
        "Reply": {"rich_text": rich(text)},
        "Status": {
            "select": {"name": STATUS_OPTED_OUT if opted_out else STATUS_REPLIED}
        },
    }
    if received_at:
        properties["Replied at"] = {"date": {"start": received_at}}

    async with session() as client:
        # Not swallowed. A dropped write here means an opt-out we were told
        # about does not reach the table, and the next run writes to them
        # again — the exact failure the five-day undertaking forbids.
        await request(client, "PATCH", f"/pages/{page_id}", json={"properties": properties})

        # The property is capped at 2000 characters; a real message can run
        # longer, and truncating the one thing a person needs to read is the
        # wrong place to economise. The page body has no such limit.
        if full_text and len(full_text) > TEXT_LIMIT:
            await _append_full_reply(client, page_id, full_text)


async def _append_full_reply(
    client: httpx.AsyncClient, page_id: str, text: str
) -> None:
    blocks = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": rich(chunk)},
        }
        for chunk in _chunks(text, TEXT_LIMIT)
    ]
    try:
        await request(
            client, "PATCH", f"/blocks/{page_id}/children",
            json={"children": blocks[:50]},
        )
    except NotionError:
        # The summary is already on the row; losing the long form is a
        # degraded read, not a missed opt-out.
        pass


def _chunks(text: str, size: int) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


async def record_message_id(page_id: str, message_id: str) -> None:
    """Store what we sent, so a reply can be matched by thread."""
    if not enabled() or not message_id:
        return
    async with session() as client:
        try:
            await request(
                client, "PATCH", f"/pages/{page_id}",
                json={"properties": {"Message ID": {"rich_text": rich(message_id)}}},
            )
        except NotionError:
            # Matching falls back to the sender address, which covers almost
            # every real reply anyway.
            pass


async def mark(page_id: str, status: str, *, error: str = "", sent_at: str = "") -> None:
    """Write the outcome back so the table is the record of what happened."""
    if not enabled():
        return
    properties: dict[str, Any] = {"Status": {"select": {"name": status}}}
    if error:
        properties["Error"] = {"rich_text": rich(error)}
    if sent_at:
        properties["Sent at"] = {"date": {"start": sent_at}}

    async with session() as client:
        # Deliberately not swallowed: if the outcome can't be written back the
        # row stays Approved, and the next poll sends a second copy to someone
        # who has already been written to.
        await request(client, "PATCH", f"/pages/{page_id}", json={"properties": properties})
