"""Draft the approach email. Drafting only — nothing here sends anything.

Pitching web work is a commercial electronic message under Australia's Spam
Act 2003, which is a different legal footing from a job enquiry. Three things
have to hold, and the draft is built to satisfy all three:

  * consent — for a business address the owner published themselves, without a
    "no unsolicited email" notice, inferred consent applies. If their contact
    page refuses unsolicited mail, don't write to them at all.
  * sender identification — the sender's real name and contact details appear
    in every message.
  * a functional opt-out — one line, honoured permanently.

https://www.acma.gov.au/avoid-sending-spam

The draft is deliberately short and specific: it names the one thing wrong
with their site and points at a demo already built. Nobody reads a pitch.
"""

import os

from loom.llm.client import Claude, Model

DRAFT_SYSTEM = """You write one short cold email from a freelance web
developer to the owner of a small local business.

Hard rules:
- Under 120 words. Owners read email on a phone between customers.
- Open with the specific, verifiable problem with their current web presence —
  the one the findings name. No flattery, no "I hope this finds you well".
- Mention the demo you already built and give the link. That is the whole
  pitch; do not describe your services or list technologies.
- No pricing, no hard sell, no urgency, no fake deadline.
- End with one low-friction question ("worth a look?").
- Sign with the sender's real name and email exactly as given.
- Then a single closing line offering to be removed from their list — plain
  wording, no marketing footer.
- Plain text. No markdown, no emoji, no subject-line label inside the body.

Output JSON only:
{"subject": str, "body": str}"""


def _sender() -> tuple[str, str]:
    """Who the message says it is from.

    The fallback address must match the mailbox that actually sends, and it
    must match the signature in config/email_templates.json. Three copies of
    one address is three chances to drift, and a From header disagreeing with
    the signature under it is both a spam signal and, under the Spam Act's
    section 17, a failure to identify the sender accurately.
    """
    from loom.services.email_templates import config

    signature = (config().get("sender") or {}).get("email", "")
    return (
        os.environ.get("OUTREACH_FROM_NAME", "Robin Peng"),
        os.environ.get("SMTP_ADDRESS")
        or os.environ.get("OUTREACH_FROM_EMAIL")
        or signature
        or "robin@robindev.org",
    )


async def draft_email(
    lead: dict, *, demo_url: str | None = None, claude: Claude | None = None
) -> dict:
    """Return {"subject", "body"} for one lead. Never sends."""
    name, email = _sender()
    audit = lead.get("audit") or {}
    findings = audit.get("findings") or []
    problems = "\n".join(
        f"- {f.get('label')}: {f.get('detail')}" for f in findings[:4]
    ) or "- They have no website at all."

    facts = [
        f"Business: {lead.get('google_name') or lead.get('site_title') or 'the business'}",
        f"Their current site: {lead.get('site_url') or 'none'}",
        f"What's wrong:\n{problems}",
        f"Demo already built: {demo_url or 'not built yet — do not mention a demo'}",
        f"Sender name: {name}",
        f"Sender email: {email}",
    ]

    claude = claude or Claude.tracked("outreach_draft")
    result = await claude.extract_json(
        "\n".join(facts), model=Model.SONNET, system=DRAFT_SYSTEM
    )
    return {
        "subject": result.get("subject", "").strip(),
        "body": result.get("body", "").strip(),
        "to": (lead.get("emails") or [None])[0],
    }
