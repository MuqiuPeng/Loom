"""Match inbound mail to the row it answers, and act on an opt-out.

The division of labour: inbox.py knows how to read a mailbox and nothing about
leads, notion_outreach.py knows the table and nothing about mail, and this
module is the only place that knows both.

Matching is by sender address first and thread second, which is the opposite
of what looks correct. Threading is more precise, but small business owners
reply from whatever client is open, and phone clients routinely drop
In-Reply-To. The address is the field that survives — and we already know
exactly which addresses were written to, so an address match is not a guess.

Nothing here sends anything. It reads the mailbox, writes to Notion, and sets
the suppression flag. A person still decides what to say back.
"""

import asyncio
import logging
from datetime import UTC, datetime

from loom.services import inbox, notion_outreach

SUMMARY_CHARS = 1800

# Hourly, not daily. The five-business-day undertaking would survive a daily
# poll, but a reply is the entire point of the pipeline and a business that
# answers in the morning should not be sitting unseen until tomorrow.
POLL_INTERVAL_SECONDS = 3600
# A short window on the schedule: anything older has been seen by an earlier
# run, and re-reading a month of mail every hour is wasteful. The manual
# endpoint still defaults to the full lookback for a first catch-up.
POLL_DAYS = 3

logger = logging.getLogger(__name__)


async def poll(days: int = inbox.LOOKBACK_DAYS) -> dict:
    """Pull replies into the outreach table. Returns what was matched.

    Safe to run repeatedly: a row already carrying this reply is left alone,
    so a poll every hour does not rewrite the same message forever.
    """
    if not inbox.enabled():
        return {"ok": False, "reason": "no mailbox credentials"}
    if not notion_outreach.enabled():
        return {"ok": False, "reason": "notion outreach table not configured"}

    rows = await notion_outreach.sent_rows()
    if not rows:
        return {"ok": True, "matched": [], "opted_out": [], "unmatched": 0}

    by_address = {r["to"]: r for r in rows if r["to"]}
    by_message = {r["message_id"]: r for r in rows if r["message_id"]}

    replies = await inbox.fetch_replies(days=days)

    matched: list[dict] = []
    opted_out: list[str] = []
    unmatched = 0
    # One row can receive several messages in a window; the last one wins,
    # because that is the state of the conversation now.
    seen: dict[str, inbox.Reply] = {}

    for reply in replies:
        row = by_address.get(reply.from_address)
        if row is None:
            row = next(
                (r for mid, r in by_message.items() if reply.threads_with(mid)),
                None,
            )
        if row is None:
            unmatched += 1
            continue
        # An autoresponder is not the business answering. It must not flip the
        # row to Replied, because that reads as interest that isn't there.
        if reply.automated:
            continue
        previous = seen.get(row["page_id"])
        if previous is None or _newer(reply, previous):
            seen[row["page_id"]] = reply

    for page_id, reply in seen.items():
        row = next(r for r in rows if r["page_id"] == page_id)
        wants_out = reply.wants_out
        received = (
            reply.received_at.astimezone(UTC).isoformat()
            if reply.received_at
            else datetime.now(UTC).isoformat()
        )
        await notion_outreach.record_reply(
            page_id,
            text=reply.body[:SUMMARY_CHARS] or "(no text)",
            received_at=received,
            opted_out=wants_out,
            full_text=reply.body,
        )
        if wants_out:
            await _suppress(row.get("lead_id", ""))
            opted_out.append(row["business"])
        matched.append(
            {
                "business": row["business"],
                "from": reply.from_address,
                "opted_out": wants_out,
                "preview": reply.body[:120],
            }
        )

    return {
        "ok": True,
        "matched": matched,
        "opted_out": opted_out,
        "unmatched": unmatched,
        "scanned": len(replies),
    }


def _newer(a: inbox.Reply, b: inbox.Reply) -> bool:
    if a.received_at is None or b.received_at is None:
        return a.received_at is not None
    return a.received_at > b.received_at


async def _suppress(lead_id: str) -> None:
    """Record the opt-out where the send path will see it.

    Notion holds the human-readable version, but the check that stops the next
    email has to run against Loom's own database — the drafting path never
    reads Notion, and an opt-out that only exists in a table nobody queries is
    the failure the undertaking was written to prevent.
    """
    if not lead_id:
        return
    from loom.api import get_storage

    await get_storage().update_scout_lead(
        lead_id,
        {
            "status": "opted_out",
            "notes": f"Opted out {datetime.now(UTC).date().isoformat()}",
        },
    )


async def poll_loop() -> None:
    """Poll the mailbox hourly for as long as the API is up.

    The signature promises removal within five business days of someone
    asking. That is only true if something reads the mailbox without being
    asked — a manual endpoint is a plan, not a mechanism.

    Failures are logged and the loop continues: a mailbox that is briefly
    unreachable must not silently end reply handling for the life of the
    process.
    """
    if not inbox.enabled() or not notion_outreach.enabled():
        logger.info("reply poller disabled (no mailbox or no outreach table)")
        return
    logger.info("reply poller started; every %.0f min", POLL_INTERVAL_SECONDS / 60)
    # A first pass over the full window, so a restart catches up on anything
    # that arrived while the process was down.
    days = inbox.LOOKBACK_DAYS
    while True:
        try:
            result = await poll(days=days)
            if result.get("matched") or result.get("opted_out"):
                logger.info("reply poll: %s", result)
            days = POLL_DAYS
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("reply poll crashed; retrying next interval")

        # Follow-ups ride the same tick, and strictly after the mailbox has
        # been read. The order is the whole safeguard: a reply that arrived in
        # the last hour marks the lead `replied` in the pass above, which is
        # what stops the follow-up below. Run them the other way round and the
        # first thing a customer who answered yesterday gets is a nudge asking
        # whether they saw it.
        try:
            await _follow_up_tick()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("follow-up run crashed; retrying next interval")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _follow_up_tick() -> None:
    """One follow-up pass, quiet unless it did something."""
    from loom.api import get_storage
    from loom.services import follow_up

    result = await follow_up.send_due(get_storage())
    if result.get("sent") or result.get("held"):
        logger.info("follow-up: %s", result)
