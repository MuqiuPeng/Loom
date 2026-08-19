"""Fill a fixed email format from lead data. No model involved.

Composing every message afresh means re-rolling the tone on every send, and
paying for it. The wording is a thing worth getting right once and then
keeping — so it lives in config/email_templates.json as slots, and this module
fills them.

Almost every slot comes straight off the lead. The audit findings in
particular are already written for the owner to read ("the page is 1208px wide
in a 375px window — it scrolls sideways"), so the sentence that makes the pitch
needs no generation at all.

The one hard rule: a template with an unfilled slot is never returned. An
email reading "Hi, I had a look at {business}" is worse than no email, and it
is exactly the failure a silent str.format swallows.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config/email_templates.json")
_SLOT_RE = re.compile(r"\{([a-z_]+)\}")


class ProblemTooWeakError(ValueError):
    """Nothing wrong with this site is worth writing to someone about."""

    def __init__(self, weight: int, minimum: int, label: str) -> None:
        super().__init__(
            f"the strongest finding is {label!r} (weight {weight}, minimum "
            f"{minimum}) — an email leading on that says you had nothing to say"
        )
        self.weight = weight


class OptedOutError(ValueError):
    """This business asked not to be written to again.

    Raised rather than returning nothing, so that a caller which ignores the
    result cannot quietly send anyway. The signature undertakes to remove
    someone from all marketing email within five business days of their
    asking, and this is the check that keeps that promise.
    """

    def __init__(self, business: str) -> None:
        super().__init__(
            f"{business} opted out — no further commercial email may be drafted"
        )


class NoConsentBasisError(ValueError):
    """Nothing establishes a right to send commercial email to this address.

    Publication is not consent — Schedule 2 clause 4(1) says so in terms. The
    exception in cl 4(2) needs the message to be relevant to the function the
    address serves, and for a careers or accounts mailbox a web-development
    offer is not. Raised rather than skipped so a caller that ignores the
    result cannot send anyway.
    """

    def __init__(self, address: str, why: str) -> None:
        # No address means there is nothing to name, and "": reason" reads as
        # a formatting fault. The reason alone is the whole answer there.
        super().__init__(f"{address}: {why}" if address else why)
        self.address = address


class MissingSlotsError(ValueError):
    """A template still had placeholders after filling."""

    def __init__(self, template: str, slots: list[str]) -> None:
        super().__init__(
            f"{template}: nothing supplied for {', '.join(sorted(slots))}"
        )
        self.slots = slots


@lru_cache(maxsize=1)
def _load(mtime: float) -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"templates": {}, "sender": {}, "defaults": {}, "signature": {}}


def config() -> dict[str, Any]:
    try:
        return _load(CONFIG_PATH.stat().st_mtime)
    except OSError:
        return {"templates": {}, "sender": {}, "defaults": {}, "signature": {}}


def available() -> list[dict[str, str]]:
    """Templates, for a picker."""
    return [
        {"key": key, "label": tpl.get("label", key)}
        for key, tpl in config().get("templates", {}).items()
    ]


def _sentence(text: str) -> str:
    """Fold a finding label into mid-sentence prose.

    "Unusable on a phone" is written as a column heading; dropped into "I had a
    look and ___" it needs to read as speech.
    """
    text = (text or "").strip().rstrip(".")
    if not text:
        return "there's a problem with it"
    return text[0].lower() + text[1:]


def slots_from_lead(lead: dict, **extra: Any) -> dict[str, str]:
    """Everything the templates can fill without asking anyone."""
    cfg = config()
    sender = cfg.get("sender", {})
    defaults = cfg.get("defaults", {})

    audit = lead.get("audit") or {}
    findings = audit.get("findings") or []
    # The worst thing wrong is what the email leads on.
    top = max(findings, key=lambda f: f.get("weight", 0)) if findings else {}

    slug = lead.get("demo_slug")
    base = (lead.get("public_base") or extra.get("public_base") or "").rstrip("/")
    # A link only exists once the demo has been made shareable. Building the
    # URL from the slug alone put an address in the email that 404s for the
    # recipient — the one link the whole message exists to deliver.
    shareable = bool(slug and base and lead.get("demo_public"))

    # Where the demo's content came from, said truthfully. "built from what's
    # already on your site" was written into the template unconditionally, and
    # is false for every lead whose site is a 404 or an unconfigured install —
    # the harvest comes back empty, the demo is assembled from placeholders,
    # and the first email a stranger sends makes a claim the owner disproves by
    # opening the page. Keyed on what the harvest actually yielded rather than
    # on whether a site_url exists, because a site that exists and holds
    # nothing is the common case, not the rare one.
    harvest = lead.get("harvest") or {}
    harvested = bool(harvest.get("menu") or harvest.get("about") or harvest.get("images"))
    notes = cfg.get("source_notes", {})
    built_from = notes.get("harvested" if harvested else "placeholder", "")

    phrases = cfg.get("problem_phrases", {})
    # The label is a column heading; the email needs a clause.
    phrase = phrases.get(top.get("code", "")) or top.get("detail", "")

    # The subject used to assert a mobile problem no matter what was actually
    # found, so a lead flagged for a wrong phone number got "your site on a
    # phone" over a body about phone numbers. A subject that misdescribes its
    # own body is how a first contact gets marked as spam.
    hooks = cfg.get("subject_hooks", {})
    hook = hooks.get(top.get("code", "")) or hooks.get("default", "your website")

    values: dict[str, str] = {
        "business": lead.get("google_name") or lead.get("site_title") or "your business",
        "site_url": lead.get("site_url") or "",
        "demo_url": f"{base}/demo/{slug}" if shareable else (lead.get("demo_url") or ""),
        "problem": top.get("label", ""),
        "problem_lower": _sentence(top.get("label", "")),
        "problem_sentence": phrase or _sentence(top.get("label", "")),
        "problem_detail": top.get("detail", ""),
        "subject_hook": hook,
        "built_from": built_from,
        "sender_name": sender.get("name", ""),
        # ACMA's guidance asks for the business name, not only a person's —
        # it is what identifies who is actually offering the service.
        "sender_business": sender.get("business", ""),
        "sender_email": sender.get("email", ""),
        "sender_phone": sender.get("phone", ""),
        # A first name is rarely known; "there" reads naturally either way.
        "contact_name": extra.get("contact_name") or "there",
        **{k: str(v) for k, v in defaults.items()},
        "timeline_capitalised": str(defaults.get("timeline", "")).capitalize(),
    }
    values.update({k: str(v) for k, v in extra.items() if v is not None})
    return values


def render(template_key: str, lead: dict, **extra: Any) -> dict[str, str]:
    """Return {"subject", "body", "to"} with every slot filled.

    Raises MissingSlots rather than sending something with a visible
    placeholder in it.
    """
    # Before anything else, and before any template is even looked up: an
    # opt-out is not a reason to draft something different, it is a reason not
    # to draft. Checked here rather than only at the send path because a
    # drafted email sitting in the approval table invites someone to approve
    # it.
    if lead.get("status") == "opted_out" or lead.get("opted_out"):
        raise OptedOutError(
            lead.get("google_name") or lead.get("site_title") or "this business"
        )

    cfg = config()
    template = cfg.get("templates", {}).get(template_key)
    if not template:
        raise KeyError(f"no template named {template_key}")

    # A cold approach has to open on something the owner would recognise.
    if template_key.startswith("first_contact"):
        audit = lead.get("audit") or {}
        findings = audit.get("findings") or []
        top = max(findings, key=lambda f: f.get("weight", 0)) if findings else {}
        minimum = cfg.get("min_problem_weight", 3)
        if top.get("weight", 0) < minimum:
            raise ProblemTooWeakError(
                top.get("weight", 0), minimum, top.get("label", "nothing")
            )

    # Which address, and whether the conspicuous-publication exception can be
    # argued for it. Done before rendering so a lead with only a careers@
    # address never becomes a draft sitting in the approval queue.
    if template_key.startswith("first_contact"):
        from loom.services import consent

        sources = lead.get("email_sources") or {}
        addresses = lead.get("emails") or []
        chosen = consent.best(addresses, sources)
        if not chosen:
            # Two different situations, and they used to produce the same
            # sentence — "(no address): unknown: not an address", which reads
            # as a bug report rather than an answer. Nothing was found is a
            # job to do; something was found but cannot be argued for is a
            # decision already made, and the reason is the useful part.
            if not addresses:
                raise NoConsentBasisError(
                    "",
                    "no email address was found on their site — their socials "
                    "or a phone call are the only way in",
                )
            reasons = []
            for address in addresses:
                _, why = consent.may_write_to(address, sources.get(address.lower()))
                reasons.append(f"{address} — {why}")
            raise NoConsentBasisError(
                addresses[0],
                "none of the addresses found can be written to: "
                + "; ".join(reasons),
            )
        extra.setdefault("chosen_address", chosen)

    values = slots_from_lead(lead, **extra)

    body = template.get("body", "")
    signature_key = template.get("needs_signature")
    if signature_key:
        body += cfg.get("signature", {}).get(signature_key, "")

    def fill(text: str) -> tuple[str, set[str]]:
        missing: set[str] = set()

        def swap(match: re.Match) -> str:
            name = match.group(1)
            value = values.get(name, "")
            if not value:
                missing.add(name)
                return match.group(0)
            return value

        return _SLOT_RE.sub(swap, text), missing

    subject, missing_subject = fill(template.get("subject", ""))
    filled_body, missing_body = fill(body)

    missing = missing_subject | missing_body
    if missing:
        raise MissingSlotsError(template_key, sorted(missing))

    # The recipient is the address with the strongest argument, not simply the
    # first one harvested: preferring owner@ over info@ is both the better
    # consent position and the better lead.
    to = extra.get("chosen_address") or (lead.get("emails") or [None])[0] or ""
    return {
        "subject": subject.strip(),
        "body": filled_body.strip(),
        "to": to,
        "template": template_key,
    }


def suggest_template(lead: dict) -> str:
    """The obvious template for where this lead currently stands."""
    if lead.get("contacted_at") and lead.get("status") == "contacted":
        return "follow_up"
    if lead.get("status") == "replied":
        return "quote"
    if lead.get("status") == "won":
        return "handover"
    # Two ways to have no website: the audit said so, or there is simply no
    # address to audit. The second was not checked, so a lead saved without a
    # site_url — which is most of what a scout finds — got the template that
    # opens by describing the site it just looked at.
    audit = lead.get("audit") or {}
    codes = {f.get("code") for f in (audit.get("findings") or [])}
    if "no_website" in codes or not (lead.get("site_url") or "").strip():
        return "first_contact_no_site"
    return "first_contact"
