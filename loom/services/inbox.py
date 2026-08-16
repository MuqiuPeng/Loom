"""Read replies to outreach, so a person can see them where they approved them.

Nothing in this pipeline could see a reply. Loom wrote to a stranger, marked
the row Sent, and then went blind — which is a problem for two reasons, one
practical and one legal.

The practical one: a reply is the whole point, and it was landing in a mailbox
nobody had a reason to open, separate from the table where the decision to
write was made.

The legal one is harder. The outreach signature now promises to remove someone
from all marketing email within five business days if they reply
"unsubscribe", and that is the Spam Act's own standard (Schedule 2 clause 6).
A promise with no mechanism behind it is worse than the vaguer wording it
replaced — ACMA's largest recent penalties are for unsubscribe failures, not
consent failures. So this module exists mainly to make sure an opt-out is
seen.

IMAP rather than the Gmail API on purpose. The mailbox host is still an open
decision — Workspace, Migadu, Purelymail and Fastmail are all in play — and
IMAP is the one interface all of them speak, using the same credential the
sender already has. An OAuth integration would tie the choice to Google.

Reading only. This module never replies, never deletes, and never marks
anything read; the mailbox is left exactly as found.
"""

import email
import imaplib
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape

from loom.services.mailer import _credentials

# Defaulted from the SMTP host where possible, because every host in the
# running names its IMAP endpoint the same way it names its SMTP one.
_IMAP_DEFAULTS = {
    "smtp.gmail.com": "imap.gmail.com",
    "smtp.migadu.com": "imap.migadu.com",
    "smtp.fastmail.com": "imap.fastmail.com",
    "smtp.purelymail.com": "imap.purelymail.com",
    "smtp.zoho.com": "imap.zoho.com",
    # Verified by connecting: both endpoints answer, and Lark advertises
    # STARTTLS on 587, so no code path changes for it.
    "smtp.larksuite.com": "imap.larksuite.com",
    "smtp.feishu.cn": "imap.feishu.cn",
}

# How far back to look. Replies arrive within days, and a wide window makes
# every poll re-read the same hundreds of messages.
LOOKBACK_DAYS = 30
MAX_MESSAGES = 200
BODY_LIMIT = 4000

# What counts as asking to be left alone.
#
# Deliberately generous, and that asymmetry is the whole design: suppressing
# someone who did not ask costs one lead, and failing to suppress someone who
# did is a breach of an undertaking we put in writing. Every ambiguous case
# resolves towards not writing to them again.
#
# "no thanks" stays in the list even though the wording that invited it has
# been replaced — people who received the old signature may still answer it.
_OPT_OUT_RE = re.compile(
    r"\bunsubscribe\b|\bopt[- ]?out\b|\bremove me\b|\btake me off\b"
    r"|\bstop (emailing|contacting|writing)\b|\bdo not (email|contact|write)\b"
    r"|\bdon'?t (email|contact|write) (me|us)\b|\bno thanks?\b"
    r"|\bnot interested\b|\bplease stop\b|\bleave me alone\b"
    r"|不要(再)?(发|联系)|退订|别再(发|联系)|取消订阅",
    re.I,
)

# Bounces and holiday autoresponders are not replies from a person. Treating a
# bounce as a reply would show "they answered!" for an address that does not
# exist, which is exactly backwards — a hard bounce means stop, not engage.
# The no-reply family is matched anywhere in the local part, not anchored to
# its start: Lark's own welcome mail comes from mail-noreply@larksuite.com and
# slipped through an anchored pattern, and prefixes like that are the norm
# rather than the exception. No real person's address contains "noreply".
#
# The role addresses stay anchored, because those are exact conventions and a
# loose match on "abuse" or "spam" would catch ordinary words.
_AUTOMATED_FROM_RE = re.compile(
    r"(no-?reply|do-?not-?reply|mailer-daemon|auto-?responder)[^@]*@"
    r"|^(postmaster|bounce[sd]?|abuse)@",
    re.I,
)
_AUTOMATED_SUBJECT_RE = re.compile(
    r"undelivered|undeliverable|delivery (status|has failed|failure)|returned mail"
    r"|out of (the )?office|auto(matic)?[- ]?repl|automatic response|away from",
    re.I,
)

# A reply quotes what it answers. Keeping the quote would put our own email
# back into the Notion row under the heading "Reply", which reads as though
# they sent it.
_QUOTE_LINE_RE = re.compile(
    r"^\s*(>|On .{0,80}wrote:|-{2,}\s*Original Message|From:\s)", re.I
)


def transport() -> str:
    """Which way in: "lark" or "imap".

    Explicit MAIL_TRANSPORT wins. Otherwise prefer Lark when its CLI is
    authorised and no SMTP password exists, because that is precisely the
    state after setting up a Lark mailbox without turning on third-party
    client access — the configuration a person actually ends up in.
    """
    choice = os.environ.get("MAIL_TRANSPORT", "").strip().lower()
    if choice in ("lark", "imap", "smtp"):
        return "imap" if choice == "smtp" else choice
    _, password = _credentials()
    if not password:
        from loom.services import lark_mail

        if lark_mail.available():
            return "lark"
    return "imap"


def enabled() -> bool:
    if transport() == "lark":
        from loom.services import lark_mail

        return lark_mail.available()
    address, password = _credentials()
    return bool(address and password)


def imap_host() -> str:
    explicit = os.environ.get("IMAP_HOST")
    if explicit:
        return explicit
    from loom.services.mailer import SMTP_HOST

    return _IMAP_DEFAULTS.get(SMTP_HOST, SMTP_HOST.replace("smtp.", "imap.", 1))


@dataclass
class Reply:
    """One inbound message, already decided about."""

    from_address: str
    from_name: str
    subject: str
    body: str
    received_at: datetime | None
    message_id: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    automated: bool = False

    @property
    def wants_out(self) -> bool:
        """Whether this reads as a request not to be written to again.

        Checked against the first part of the message only. A quoted copy of
        our own signature contains the word "unsubscribe", so scanning the
        whole body would mark every single reply as an opt-out.
        """
        if self.automated:
            return False
        return bool(_OPT_OUT_RE.search(self.body[:800]))

    def threads_with(self, message_id: str) -> bool:
        if not message_id:
            return False
        return message_id in (self.in_reply_to, *self.references)


def _decoded(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except (UnicodeDecodeError, LookupError, ValueError):
        return raw


def _plain_body(message: email.message.Message) -> str:
    """The text/plain part, or the closest thing to it."""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = message.get_payload(decode=True)
    if not payload:
        return ""
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def strip_quoted(text: str) -> str:
    """Just what this person wrote, without the copy of our own email."""
    kept: list[str] = []
    for line in text.splitlines():
        if _QUOTE_LINE_RE.match(line):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def _parse(raw: bytes) -> Reply | None:
    try:
        message = email.message_from_bytes(raw)
    except Exception:
        return None

    name, address = parseaddr(_decoded(message.get("From")))
    if not address:
        return None
    subject = _decoded(message.get("Subject"))

    try:
        received = parsedate_to_datetime(message.get("Date", ""))
    except (TypeError, ValueError):
        received = None

    body = strip_quoted(_plain_body(message))[:BODY_LIMIT]
    references = (message.get("References") or "").split()

    return Reply(
        from_address=address.lower(),
        from_name=name,
        subject=subject,
        body=body,
        received_at=received,
        message_id=(message.get("Message-ID") or "").strip(),
        in_reply_to=(message.get("In-Reply-To") or "").strip(),
        references=references,
        automated=bool(
            _AUTOMATED_FROM_RE.search(address)
            or _AUTOMATED_SUBJECT_RE.search(subject)
            # RFC 3834. Set by well-behaved autoresponders precisely so that
            # software like this does not mistake them for a person.
            or message.get("Auto-Submitted", "no").lower() != "no"
            or message.get("X-Autoreply")
            or message.get("Precedence", "").lower() in ("bulk", "auto_reply")
        ),
    )


def _fetch_blocking(days: int, limit: int) -> list[Reply]:
    address, password = _credentials()
    host = imap_host()
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%d-%b-%Y")

    connection = imaplib.IMAP4_SSL(host, timeout=30)
    try:
        connection.login(address, password)
        # readonly: this must never mark anything seen. The mailbox belongs to
        # a person who may not have read these yet.
        connection.select("INBOX", readonly=True)
        status, data = connection.search(None, f'(SINCE "{since}")')
        if status != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()[-limit:]

        replies: list[Reply] = []
        for message_id in ids:
            status, payload = connection.fetch(message_id, "(RFC822)")
            if status != "OK" or not payload:
                continue
            for part in payload:
                if isinstance(part, tuple) and part[1]:
                    parsed = _parse(part[1])
                    if parsed:
                        replies.append(parsed)
                    break
        return replies
    finally:
        try:
            connection.logout()
        except Exception:
            pass


_BR_RE = re.compile(r"<br\s*/?>|</(p|div|tr|li|h[1-6])\s*>", re.I)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _text_from_lark(full: dict) -> str:
    """The message body with its line structure intact.

    Lark's `body_plain_text` is flattened — every newline is gone, the whole
    message arrives as one line. That silently breaks strip_quoted(), which
    works line by line, so a reply quoting our own email would keep the quote
    — including the word "unsubscribe" from our signature — and could be read
    as an opt-out from someone who was actually saying yes.

    The HTML body keeps the structure as <br>, so rebuild the newlines from
    that and fall back to the flat text only if there is no HTML.
    """
    html = full.get("body_html") or ""
    if not html:
        return full.get("body_plain_text") or ""
    text = _BR_RE.sub("\n", html)
    text = _HTML_TAG_RE.sub("", text)
    return unescape(text).replace("\xa0", " ")


def _from_lark(summary: dict, full: dict) -> Reply | None:
    """One Lark message in the same shape IMAP produces.

    Lark exposes no In-Reply-To or References — it threads with its own
    thread_id instead — so `references` carries the thread id. Matching a
    reply to a lead still works, because that is done on the sender's address
    first and the header only as a fallback.
    """
    head = full.get("head_from") or {}
    sender = (head.get("mail_address") or "").lower()
    if not sender:
        return None

    subject = full.get("subject") or summary.get("subject") or ""
    stamp = full.get("internal_date")
    received = None
    if stamp:
        try:
            received = datetime.fromtimestamp(int(stamp) / 1000, tz=UTC)
        except (TypeError, ValueError, OSError):
            received = None

    thread = full.get("thread_id") or summary.get("thread_id") or ""
    return Reply(
        from_address=sender,
        from_name=head.get("name") or "",
        subject=subject,
        body=strip_quoted(_text_from_lark(full))[:BODY_LIMIT],
        received_at=received,
        # The real RFC Message-ID, which Lark keeps alongside its own id.
        message_id=(full.get("smtp_message_id") or "").strip(),
        in_reply_to="",
        references=[thread] if thread else [],
        automated=bool(
            _AUTOMATED_FROM_RE.search(sender)
            or _AUTOMATED_SUBJECT_RE.search(subject)
        ),
    )


async def _fetch_lark(days: int, limit: int) -> list[Reply]:
    from loom.services import lark_mail

    summaries = await lark_mail.recent(days=days, limit=limit)
    replies: list[Reply] = []
    for summary in summaries:
        message_id = summary.get("message_id")
        if not message_id:
            continue
        try:
            full = await lark_mail.message(message_id)
        except lark_mail.LarkMailError:
            # One unreadable message must not lose the rest of the poll.
            continue
        parsed = _from_lark(summary, full)
        if parsed:
            replies.append(parsed)
    return replies


async def fetch_replies(
    days: int = LOOKBACK_DAYS, limit: int = MAX_MESSAGES
) -> list[Reply]:
    """Recent inbound mail, parsed. Raises if the mailbox can't be reached."""
    import asyncio

    if not enabled():
        raise RuntimeError(
            "no mailbox access — authorise lark-cli, or set SMTP_ADDRESS "
            "and SMTP_PASSWORD"
        )
    if transport() == "lark":
        return await _fetch_lark(days, limit)
    return await asyncio.to_thread(_fetch_blocking, days, limit)
