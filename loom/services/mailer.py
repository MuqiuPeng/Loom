"""Send an approved email, and nothing else.

Every safeguard in this file exists because the thing being automated is
"contact a stranger on someone's behalf", and the failure modes are not
recoverable: a duplicate, a wrong recipient, or a send that was never approved
all land in a real person's inbox.

So:

  * this module never decides to send anything — it is handed rows that a
    human has already marked Approved in Notion
  * the outcome is written back before anything else happens, so a crash
    cannot produce a second copy
  * a dry run is the default until SMTP credentials exist, which means the
    first time anyone runs the poller it reports what it would have done

Gmail wants an app password, not the account password: Google Account →
Security → 2-Step Verification → App passwords. Put it in .env as
GMAIL_APP_PASSWORD alongside GMAIL_ADDRESS.
"""

import asyncio
import os
import random
import re
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from loom.services.dns_check import deliverable

# Configurable because the host is a decision that should cost a .env line,
# not a code change. Google Workspace also answers on smtp.gmail.com, so
# moving to a custom domain there needs nothing here — but Migadu, Purelymail,
# Fastmail and Zoho each have their own host, and at roughly a hundred dollars
# a year between them that choice should stay open.
#
# The env names still say GMAIL_ for compatibility with what is already in
# .env; SMTP_ADDRESS and SMTP_PASSWORD are read first so a non-Google host can
# be configured without keeping a misleading name.
SMTP_HOST = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 587)


def _credentials() -> tuple[str, str]:
    return (
        os.environ.get("SMTP_ADDRESS") or os.environ.get("GMAIL_ADDRESS", ""),
        os.environ.get("SMTP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD", ""),
    )

# Well under Gmail's documented 500/day, because the ceiling was never the
# constraint — complaints are. A run that sends twenty and stops is also a run
# whose damage is bounded when something is wrong with the drafts.
MAX_PER_RUN = 20
# Jitter, not a fixed gap: fifty identical intervals is itself a pattern, and
# each send currently opens a fresh TLS+AUTH cycle.
SEND_GAP_SECONDS = (30, 90)

# Addresses that are never a person. noreply/donotreply bounce or black-hole;
# the abuse/postmaster family are the ones most likely to be spamtraps, and
# writing to them is how a sending identity gets reported rather than ignored.
_NEVER_SEND = re.compile(
    r"^(no[-_.]?reply|donot(reply)?|do[-_.]?not[-_.]?reply|bounce|mailer[-_.]?daemon"
    r"|abuse|postmaster|spam|hostmaster|webmaster|security)@",
    re.I,
)


def transport() -> str:
    """Which way out: "lark" or "smtp".

    Mirrors inbox.transport() so the two halves never disagree — reading
    replies from one mailbox while sending from another would break the
    matching that the opt-out obligation rests on.
    """
    from loom.services.inbox import transport as inbound

    return "lark" if inbound() == "lark" else "smtp"


def redirect_to() -> str:
    """An address that every outbound message goes to instead of its recipient.

    Set OUTREACH_REDIRECT_TO while the pipeline is being trialled, so the
    whole path — drafting, approval, transport, the Notion write-back — runs
    against real leads without a stranger receiving anything.

    Intercepted in send() rather than in send_approved() because send() is the
    one choke point every path goes through, including the test script and
    anything added later. A guard one level up is a guard something will
    eventually route around.
    """
    return (os.environ.get("OUTREACH_REDIRECT_TO") or "").strip()


def _redirected(to: str, subject: str, body: str) -> tuple[str, str]:
    """The subject and body to use when a message is being diverted.

    Loud on purpose. A redirect that reads like an ordinary sent message is
    how someone concludes they have contacted twenty businesses when they
    have contacted none.
    """
    banner = (
        "┌─────────────────────────────────────────────────────────────\n"
        "│ REDIRECTED — this was NOT sent to the business.\n"
        f"│ Intended recipient: {to}\n"
        f"│ Original subject:   {subject}\n"
        "│ Unset OUTREACH_REDIRECT_TO in .env to send for real.\n"
        "└─────────────────────────────────────────────────────────────\n\n"
    )
    return f"[REDIRECTED → {to}] {subject}", banner + body


def html_body(body: str, *, image_cid: str = "", image_alt: str = "") -> str:
    """An HTML rendering of the body, or "" to send it as plain text.

    Off unless OUTREACH_HTML is set. A cold approach from one person is
    normally better plain: HTML from an unknown sender is the shape of
    marketing, and the research on this said a missing plain-text alternative
    counts against you. The renderer exists so the choice can be made on
    evidence rather than assumption.
    """
    if (os.environ.get("OUTREACH_HTML") or "").strip().lower() not in ("1", "true", "yes"):
        return ""
    from loom.services.email_html import to_html

    return to_html(body, image_cid=image_cid, image_alt=image_alt)


def configured() -> bool:
    if transport() == "lark":
        from loom.services import lark_mail

        return lark_mail.available()
    address, password = _credentials()
    return bool(address and password)


def sendable(to: str) -> str:
    """The reason this address must not be written to, or "" if it's fine."""
    if not to or "@" not in to:
        return f"{to!r} is not an address"
    if _NEVER_SEND.match(to.strip()):
        return f"{to} is an unattended or trap address"
    return ""


def _build(
    to: str, subject: str, body: str, *, in_reply_to: str = ""
) -> EmailMessage:
    address, _ = _credentials()
    name = os.environ.get("OUTREACH_FROM_NAME", "")

    message = EmailMessage()
    message["From"] = formataddr((name, address)) if name else address
    message["To"] = to
    message["Subject"] = subject
    message["Reply-To"] = address
    # Date and Message-ID were both missing. SpamAssassin scores their absence
    # at roughly 2.7 and 1.2 against a threshold of 5, so two absent headers
    # were carrying a cold email most of the way to a spam verdict on their
    # own — and Gmail has been known to reject outright on a missing
    # Message-ID. smtplib does not supply either.
    message["Date"] = formatdate(localtime=True)
    domain = address.rsplit("@", 1)[-1] or None
    message["Message-ID"] = make_msgid(domain=domain)
    if in_reply_to:
        # The follow-up subject starts with "Re:". Without these it is a
        # fake reply — a documented spam signal, and it also means the
        # follow-up won't thread in the recipient's client.
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to
    # A plain-text body is what a shop owner's phone renders best.
    message.set_content(body)
    return message


def _send_blocking(
    to: str, subject: str, body: str, in_reply_to: str
) -> str:
    message = _build(to, subject, body, in_reply_to=in_reply_to)
    address, password = _credentials()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(address, password)
        server.send_message(message)
    # Handed back so a follow-up can thread against the first contact.
    return str(message["Message-ID"])


async def send(
    to: str, subject: str, body: str, *,
    in_reply_to: str = "", preview_html: str = "", preview_alt: str = "",
) -> str:
    """Send one message and return its Message-ID.

    Raises on failure; the caller records the outcome.
    """
    if not configured():
        raise RuntimeError(
            "no way to send — authorise lark-cli, or set SMTP_ADDRESS and "
            "SMTP_PASSWORD — nothing was sent"
        )
    refusal = sendable(to)
    if refusal:
        raise ValueError(f"refusing to send: {refusal}")

    # After the recipient gates, so a redirected run still exercises them and
    # still reports a bad address rather than hiding it.
    divert = redirect_to()
    if divert:
        subject, body = _redirected(to, subject, body)
        to = divert

    if transport() == "lark":
        from loom.services import lark_mail

        # Lark composes and signs the message itself, so the Date and
        # Message-ID that _build() adds by hand are its problem rather than
        # ours. Threading is by its own thread id, not In-Reply-To.
        rich = html_body(body)
        inline: list[dict[str, str]] = []
        cid = ""
        if rich and preview_html:
            cid, path = await _preview_image(preview_html)
            if cid:
                inline = [{"cid": cid, "file_path": path}]
                rich = html_body(body, image_cid=cid, image_alt=preview_alt)
        try:
            return await lark_mail.send(to, subject, body, html=rich, inline=inline)
        finally:
            _discard_preview(inline)
    # smtplib is blocking; keep it off the event loop.
    return await asyncio.to_thread(_send_blocking, to, subject, body, in_reply_to)


def _is_quota_exhausted(exc: Exception) -> bool:
    """Whether Gmail has cut us off for the day.

    Matched on the enhanced status code rather than the prose: Google's docs
    say "Daily user sending limit exceeded" while the live server often says
    "quota exceeded", and 5.4.5 is the part that doesn't move. 4.7.x is
    transient and 5.2.1 is the recipient's mailbox, neither of which should
    stop a run.
    """
    return "5.4.5" in str(exc)


async def send_approved(dry_run: bool | None = None) -> dict:
    """Send everything a human approved in Notion. Returns what happened.

    dry_run defaults to "whenever SMTP isn't configured", so running this
    before credentials exist reports the queue instead of failing.
    """
    from loom.services import notion_outreach

    if dry_run is None:
        dry_run = not configured()

    rows = await notion_outreach.approved_rows()
    diverting = redirect_to()
    sent: list[str] = []
    redirected: list[dict] = []
    # Each failure carries why, because "3 failed" with no reason is a
    # result nobody can act on.
    failed: list[dict] = []
    skipped: list[dict] = []
    halted = ""
    # The queue used to be walked end to end with no pause and no ceiling,
    # opening a fresh TLS+AUTH cycle each time. Fifty of those back to back is
    # a flag in its own right, and it means one bad batch of drafts reaches
    # fifty strangers before anyone can look.
    due = rows[:MAX_PER_RUN]
    deferred = [r.get("business") or r["page_id"] for r in rows[MAX_PER_RUN:]]

    for index, row in enumerate(due):
        label = row.get("business") or row.get("page_id")

        # Both gates run in a dry run too — reporting which addresses are
        # unusable is most of what a dry run is for — but neither writes to
        # Notion unless something is really being sent. A dry run that mutates
        # the table is not a dry run.
        #
        # The DNS answer is asked for at send time rather than at drafting
        # time because a draft can sit in the queue for days. Only a definite
        # "this domain cannot receive mail" stops the send: an unanswerable
        # lookup returns None and the email goes, since blocking a real
        # customer over our own DNS trouble is worse than the bounce.
        refusal = sendable(row.get("to") or "")
        if not refusal and await deliverable(row["to"]) is False:
            refusal = f"{row['to']} — the domain can't receive mail"

        if refusal:
            if not dry_run:
                await notion_outreach.mark(
                    row["page_id"], notion_outreach.STATUS_FAILED, error=refusal,
                )
            failed.append({"business": label, "reason": refusal})
            continue

        if dry_run:
            skipped.append({"business": label, "to": row["to"]})
            continue

        if index:
            # Spread the run out. Cheap insurance, and the only cost is that a
            # batch of twenty takes half an hour instead of twenty seconds.
            await asyncio.sleep(random.uniform(*SEND_GAP_SECONDS))

        try:
            message_id = await send(row["to"], row["subject"], row["body"])
        except Exception as e:
            await notion_outreach.mark(
                row["page_id"], notion_outreach.STATUS_FAILED, error=str(e)[:300]
            )
            failed.append({"business": label, "reason": str(e)[:200]})
            if _is_quota_exhausted(e):
                # Every remaining row would fail the same way, and each
                # attempt is another strike against an account that is
                # already being throttled. Stop, and leave them Approved so
                # the next run picks them up.
                halted = str(e)[:200]
                break
            continue

        if diverting:
            # Deliberately NOT marked Sent, and contacted_at stays null. The
            # business was not written to, so recording it as contacted would
            # make the next run think first contact had happened and jump
            # straight to a follow-up nobody ever received the start of. The
            # row stays Approved so a real run still picks it up.
            redirected.append({"business": label, "would_have_gone_to": row["to"]})
            continue

        await notion_outreach.mark(
            row["page_id"],
            notion_outreach.STATUS_SENT,
            sent_at=datetime.now(UTC).isoformat(),
        )
        sent.append(label)
        await _record_contact(row, message_id)
        # Stored on the row so an inbound message can be matched to it by
        # thread when the sender replies from a different address than the
        # one we wrote to — a shared info@ answered by the owner personally.
        await notion_outreach.record_message_id(row["page_id"], message_id)

        try:
            from loom.services.logger import logger as loom_logger
            await loom_logger.info(
                "user_action", "outreach.sent",
                f"Sent approved email to {row['to']}",
                service="company_scout", to=row["to"], business=label,
                lead_id=row.get("lead_id"), message_id=message_id,
            )
        except Exception:
            pass

    return {
        "dry_run": dry_run,
        "approved": len(rows),
        "sent": sent,
        "failed": failed,
        "would_send": skipped,
        "deferred": deferred,
        "halted": halted,
        # Named prominently rather than folded into `sent`: the difference
        # between "twenty businesses were contacted" and "twenty test copies
        # reached you" is the whole point of the setting.
        "redirected_to": diverting,
        "redirected": redirected,
    }


async def _record_contact(row: dict, message_id: str) -> None:
    """Mark the lead contacted in Loom's own database.

    Notion held the only record that a message had gone out, so `contacted_at`
    on the lead stayed null forever — which meant suggest_template() never
    advanced a lead to follow_up, and nothing in Loom could answer "have we
    already written to these people?". A record of who has been contacted is
    also what an opt-out has to be checked against.
    """
    lead_id = row.get("lead_id")
    if not lead_id:
        return
    try:
        from loom.api import get_storage

        await get_storage().update_scout_lead(
            lead_id,
            {
                "contacted_at": datetime.now(UTC).replace(tzinfo=None),
                "status": "contacted",
            },
        )
    except Exception:
        # Notion already says Sent, and that is the record that prevents a
        # duplicate. Failing to mirror it here must not fail the run.
        pass


# ── inline preview ───────────────────────────────────────────────────
#
# Lark takes inline attachments as paths relative to the working directory
# and refuses absolute ones, so the JPEG has to be written inside the repo.
# .loom-tmp is gitignored and each file is removed as soon as the send
# returns — a directory of stale screenshots of other people's businesses is
# not something to accumulate.
PREVIEW_DIR = ".loom-tmp"
PREVIEW_WIDTH = 420
# Tall enough for the hero — photograph, name, tagline — and no taller.
# Past that the page is body copy that reads as grey mush at thumbnail size
# while still costing kilobytes.
PREVIEW_HEIGHT = 520
PREVIEW_QUALITY = 78


async def _preview_image(demo_html: str) -> tuple[str, str]:
    """Render the demo to a JPEG. Returns (cid, relative path), or ("", "").

    Failure is silent by design: an email that goes without its picture is a
    worse email, but an email that does not go at all because a headless
    browser was unavailable is a lost lead.
    """
    try:
        from loom.services.render_check import screenshot

        image = await screenshot(
            demo_html, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT,
            quality=PREVIEW_QUALITY,
        )
        if not image:
            return "", ""
        import pathlib
        import uuid

        folder = pathlib.Path(PREVIEW_DIR)
        folder.mkdir(exist_ok=True)
        cid = uuid.uuid4().hex[:16]
        path = folder / f"{cid}.jpg"
        path.write_bytes(image)
        return cid, str(path)
    except Exception:
        return "", ""


def _discard_preview(inline: list[dict[str, str]]) -> None:
    import contextlib
    import pathlib

    for item in inline:
        with contextlib.suppress(OSError):
            pathlib.Path(item["file_path"]).unlink()
