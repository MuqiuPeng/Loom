"""Send the one follow-up, at the right time, to the leads still owed it.

A follow-up is the cheapest thing in cold outreach: the message is already
written, the demo is already built, and the recipient has already been chosen
and argued for. What was missing was anything that noticed the day had come.
`suggest_template` has returned "follow_up" for a contacted lead since the
templates were written; nothing ever asked it.

ONE, and then stop. The template is labelled "Follow-up (once, then stop)" and
its body tells the recipient as much — "just say so and I won't write again".
A second follow-up is a separate commercial electronic message needing the same
consent basis as the first, sent to someone who has now ignored two, from an
address that promised restraint. The gain is not worth what it costs the
sentence.

WHEN. Three business days, counted in weekdays, so a Friday approach is
followed up on Wednesday rather than on Monday morning with the weekend
counted as thinking time. Sent inside working hours in the recipient's own
timezone, because the poller runs hourly and 3am is a tell.

WHY IT STOPS. The interesting half of this module is the refusals, and every
one of them is a real way to embarrass someone:

  * they replied — the poller writes `replied` before this runs, and the two
    running in that order is the point, not a coincidence
  * they opted out — render() raises before a body is built, but the check is
    here too, because the one thing that must never happen is worth two locks
  * the deal is won or dead
  * it already went
  * too long ago — a follow-up to a two-month-old note is not a follow-up, it
    is a second cold approach wearing "Re:"

Everything about the send itself — the denylist, the redirect, the per-run cap,
the gap between messages — belongs to mailer and is not repeated here.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# Weekdays between the first approach and the follow-up.
WAIT_BUSINESS_DAYS = 3

# Past this, the thread is cold and "Re:" is a costume. Counted in calendar
# days because that is how the recipient experiences it.
STALE_AFTER_DAYS = 30

# The recipient's working day, not the server's. Fly runs in syd and the
# machine is UTC; neither is where the shop is.
LOCAL = ZoneInfo("Australia/Sydney")
HOUR_OPEN = 8
HOUR_CLOSE = 17

# Statuses that mean the conversation moved on. Anything not here — chiefly
# "contacted" — is a lead still waiting to hear back.
SETTLED = {"replied", "opted_out", "won", "lost", "not_interested"}


def business_days_between(start: datetime, end: datetime) -> int:
    """Weekdays from `start` to `end`, not counting the day it was sent.

    Day counting, not hour counting: an approach at 4pm Monday and one at 9am
    Monday are the same distance from Thursday as anyone reading them measures
    it.
    """
    if end <= start:
        return 0
    days = 0
    cursor = start.date()
    last = end.date()
    while cursor < last:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days


def in_working_hours(now: datetime) -> bool:
    """Whether now is a weekday business hour where the recipient is."""
    local = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(LOCAL)
    return local.weekday() < 5 and HOUR_OPEN <= local.hour < HOUR_CLOSE


def _at(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def due(lead: dict, now: datetime) -> tuple[bool, str]:
    """Whether this lead is owed its follow-up, and what stopped it if not.

    The reason is returned rather than logged so a caller can show a person why
    a lead they expected to see is not in the list. A silent "no" here looks
    exactly like a scheduler that has stopped running.
    """
    # The invariant from the top of the pipeline: commercial outreach runs on
    # freelance leads only. A job-hunt lead must never be chased with a pitch.
    if lead.get("kind") != "freelance":
        return False, "not a freelance lead"

    contacted = _at(lead.get("contacted_at"))
    if not contacted:
        return False, "never contacted"
    if _at(lead.get("followed_up_at")):
        return False, "already followed up"
    if lead.get("opted_out") or lead.get("status") == "opted_out":
        return False, "opted out"
    if lead.get("status") in SETTLED:
        return False, f"status is {lead.get('status')}"
    if not lead.get("demo_slug") or not lead.get("demo_public"):
        # The whole message is "the mock-up is still up". It has to be up.
        return False, "no shareable demo to point at"

    if (now - contacted).days > STALE_AFTER_DAYS:
        return False, f"contacted more than {STALE_AFTER_DAYS} days ago"

    waited = business_days_between(contacted, now)
    if waited < WAIT_BUSINESS_DAYS:
        return False, f"{waited} of {WAIT_BUSINESS_DAYS} business days"
    if not in_working_hours(now):
        return False, "outside the recipient's working hours"

    return True, ""


def pending(leads: list[dict], now: datetime) -> list[dict]:
    """The leads due a follow-up right now."""
    return [lead for lead in leads if due(lead, now)[0]]


async def send_due(storage, *, now: datetime | None = None, dry_run: bool = False) -> dict:
    """Send the follow-up to every lead owed one. Returns what happened.

    The send guards — the never-send denylist, the redirect, the gap between
    messages — all live in mailer and are not restated. What is restated is the
    redirect's own rule, because it applies here for the same reason: a
    diverted message did not reach the business, so recording it as sent would
    burn the one follow-up on a message nobody received. The queue keeps
    contacted_at null for exactly this; this keeps followed_up_at null.
    """
    import asyncio
    import os
    import random

    from loom.services import mailer
    from loom.services.email_templates import (
        MissingSlotsError,
        NoConsentBasisError,
        OptedOutError,
        render,
    )

    now = now or datetime.utcnow()
    diverting = mailer.redirect_to()

    leads = [await storage.get_scout_lead(r["id"]) for r in await storage.list_scout_leads()]
    owed = pending([lead for lead in leads if lead], now)

    sent: list[dict] = []
    held: list[dict] = []
    for index, lead in enumerate(owed):
        label = lead.get("google_name") or lead.get("site_title") or lead["id"]
        try:
            # The whole message is a link to the demo, so the host it lives
            # on has to come in the same way the first contact gets it. Left
            # out, render raises MissingSlots rather than sending a follow-up
            # whose one useful line is blank — which is how this was caught.
            draft = render(
                "follow_up",
                lead,
                public_base=os.environ.get("LOOM_PUBLIC_URL", ""),
            )
        except (OptedOutError, NoConsentBasisError, MissingSlotsError) as e:
            # Consent is re-argued at follow-up time rather than inherited from
            # the first contact: a page that has since added a refusal notice,
            # or an address that has gone, changes the answer.
            held.append({"business": label, "reason": str(e)[:160]})
            continue

        refusal = mailer.sendable(draft["to"])
        if refusal:
            held.append({"business": label, "reason": refusal})
            continue

        if dry_run:
            held.append({"business": label, "reason": "dry run", "to": draft["to"]})
            continue

        if index:
            await asyncio.sleep(random.uniform(*mailer.SEND_GAP_SECONDS))

        try:
            await mailer.send(draft["to"], draft["subject"], draft["body"])
        except Exception as e:
            held.append({"business": label, "reason": str(e)[:160]})
            continue

        if diverting:
            held.append({"business": label, "reason": f"diverted to {diverting}"})
            continue

        await storage.update_scout_lead(lead["id"], {"followed_up_at": now})
        sent.append({"business": label, "to": draft["to"]})

    if sent or held:
        log.info("follow-up run: %d sent, %d held", len(sent), len(held))
    return {"sent": sent, "held": held, "considered": len(leads)}
