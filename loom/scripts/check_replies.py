"""Check the reply reader and the opt-out gate. Fully offline.

Run after any change to inbox.py, replies.py or the outreach signature.

The cases here are not hypothetical. Two of them are the failures that would
actually happen: our own signature contains the word "unsubscribe", so a
customer who quotes the email back while saying "call me" would be marked as
opting out and never contacted again; and an out-of-office autoreply would
flip the row to Replied, which reads as interest that is not there.

The opt-out gate matters more than the detection. The outreach signature now
undertakes to remove someone from all marketing email within five business
days, and these assertions are what keeps that promise true.

    python -m loom.scripts.check_replies

Exits non-zero on any failure.
"""

import email.message
import sys
from typing import Any

from loom.services.email_templates import OptedOutError, render
from loom.services.inbox import Reply, _parse, strip_quoted

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}")
        failures.append(label)


def make(
    frm: str = "owner@cafe.com.au",
    subject: str = "Re: Ferro Plumbing",
    body: str = "Sounds good",
    extra: dict[str, str] | None = None,
) -> Reply:
    message = email.message.EmailMessage()
    message["From"] = frm
    message["To"] = "robin@robindev.org"
    message["Subject"] = subject
    message["Date"] = "Sat, 16 Aug 2026 09:15:00 +1000"
    message["Message-ID"] = "<reply-1@cafe.com.au>"
    message["In-Reply-To"] = "<sent-1@robindev.org>"
    for key, value in (extra or {}).items():
        message[key] = value
    message.set_content(body)
    parsed = _parse(message.as_bytes())
    assert parsed is not None
    return parsed


def opt_out_checks() -> None:
    print("opt-out detection:")
    cases = [
        ("unsubscribe", True),
        ("Please remove me from your list.", True),
        ("Not interested, thanks.", True),
        ("no thanks", True),
        ("Please stop emailing me", True),
        ("退订", True),
        ("不要再发了", True),
        ("Yes! Can you call me Tuesday?", False),
        ("How much for the whole thing?", False),
        ("Looks great, send me a quote", False),
    ]
    for body, want in cases:
        check(make(body=body).wants_out == want, f"{body[:38]!r}")


def quoting_checks() -> None:
    print("\nour own signature quoted back:")
    quoted = (
        "Sounds interesting, call me.\n\n"
        "On Sat, 16 Aug 2026, Robin Peng wrote:\n"
        '> If you\'d rather not hear from us, reply with "unsubscribe" and\n'
        "> we'll remove you from all our marketing email.\n"
    )
    reply = make(body=quoted)
    check(not reply.wants_out, "a quoted signature is not read as an opt-out")
    check("unsubscribe" not in reply.body, "the quote is stripped from stored text")
    check(reply.body == "Sounds interesting, call me.", "only their words are kept")

    print("\nquote markers recognised:")
    for raw in (
        "hi\n\n> quoted",
        "hi\n\nOn Sat, someone wrote:\nstuff",
        "hi\n\n-- Original Message --\nstuff",
        "hi\n\nFrom: robin\nstuff",
    ):
        check(strip_quoted(raw) == "hi", repr(raw[4:26]))


def automated_checks() -> None:
    print("\nautomated mail is not a reply:")
    cases: list[tuple[dict[str, Any], bool]] = [
        ({"frm": "mailer-daemon@googlemail.com"}, True),
        # Lark's own welcome mail, which an anchored pattern missed.
        ({"frm": "mail-noreply@larksuite.com"}, True),
        ({"frm": "noreply-alerts@shop.com.au"}, True),
        ({"frm": "bounces@list.example"}, True),
        # Must NOT fire: ordinary people whose names brush the keywords.
        ({"frm": "rep.lyle@cafe.com.au"}, False),
        ({"frm": "abusaid@bakery.com.au"}, False),
        ({"subject": "Undelivered Mail Returned to Sender"}, True),
        ({"subject": "Out of Office: back Monday"}, True),
        ({"extra": {"Auto-Submitted": "auto-replied"}}, True),
        ({"extra": {"Precedence": "bulk"}}, True),
        ({}, False),
    ]
    for kwargs, want in cases:
        label = str(kwargs)[:52] if kwargs else "a normal reply"
        check(make(**kwargs).automated == want, label)
    check(
        not make(subject="Out of Office", body="unsubscribe").wants_out,
        "an autoresponder containing the word is still not an opt-out",
    )


def matching_checks() -> None:
    print("\nthreading and address parsing:")
    reply = make()
    check(reply.threads_with("<sent-1@robindev.org>"), "matches by In-Reply-To")
    check(not reply.threads_with("<other@robindev.org>"), "no match on a foreign id")
    check(not reply.threads_with(""), "an empty stored id never matches")
    check(reply.from_address == "owner@cafe.com.au", "address extracted")
    check(
        make(frm="Jo Owner <JO@Cafe.com.AU>").from_address == "jo@cafe.com.au",
        "mixed-case address normalised",
    )


LEAD = {
    "id": "t",
    "google_name": "Ferro Plumbing",
    "site_url": "https://x.example",
    "demo_slug": "f",
    "demo_public": True,
    # A role address the exception can be argued for; "a@b.com" is a named
    # individual with no stated role and is now correctly refused.
    "emails": ["owner@cafe.com.au"],
    "audit": {
        "findings": [
            {"code": "phone_not_tappable", "weight": 3, "label": "x", "detail": "y"}
        ]
    },
}


def gate_checks() -> None:
    print("\nopt-out gate:")

    def blocked(lead: dict, template: str = "first_contact") -> bool:
        try:
            render(template, lead, public_base="https://p")
        except OptedOutError:
            return True
        return False

    check(not blocked(LEAD), "a lead that never opted out still drafts")
    check(blocked({**LEAD, "status": "opted_out"}), "status=opted_out blocks drafting")
    check(blocked({**LEAD, "opted_out": True}), "an opted_out flag blocks drafting")
    check(
        blocked({**LEAD, "status": "opted_out", "contacted_at": "x"}, "follow_up"),
        "the follow-up is blocked too, not only first contact",
    )


def html_checks() -> None:
    """The HTML renderer, and the two ways it has already gone wrong."""
    from loom.services.email_html import to_html

    print("\nhtml rendering:")
    body = (
        "Hi,\n\n"
        "I had a look at Ferro Plumbing and your number is plain text.\n\n"
        "I rebuilt it as it could be:\n"
        "https://loom.robindev.org/demo/ferro-abc\n\n"
        "It's a mock-up. AUD $900.\n\n"
        "Worth a look?\n\n"
        "\u2014\nRobin Peng\nrobin@robindev.org\n\n"
        'If you\'d rather not hear from us, reply with "unsubscribe".'
    )
    out = to_html(body)

    check("<img" not in out.lower(), "no images — a tracking-pixel shape is a spam signal")
    check(out.lower().count("<a ") == 1, "exactly one link")
    check("border-radius" in out, "the demo panel is drawn")
    check("Georgia" in out, "the finding is set in the serif face")
    check("<hr" in out, "the sign-off rule is drawn")
    # The separator used to arrive as "\u2014\nRobin Peng\n..." in one block, so
    # comparing the whole block against the mark never matched: no rule was
    # drawn and the dash showed as literal text above the name.
    check("\u2014" not in out.replace("&mdash;", ""),
          "the sign-off dash became the rule, not literal text")
    check("Robin Peng" in out, "the signature survives the separator handling")
    check(out.index("unsubscribe") > out.index("Robin Peng"),
          "the opt-out stays below the signature")
    for word in ("Ferro Plumbing", "AUD $900", "Worth a look?"):
        check(word in out, f"{word!r} carried through unchanged")

    print("\ninline screenshot:")
    shot = to_html(body, image_cid="abc123", image_alt="The rebuilt page")
    check(shot.lower().count("<img") == 1, "exactly one image, never more")
    check("cid:abc123" in shot,
          "referenced by content-id, not a remote URL that blocking would empty")
    check('alt="The rebuilt page' in shot,
          "carries a description in alt text")
    check(shot.index("<img") > shot.index("Georgia"),
          "the image sits below the finding, not above it")
    check("<img" not in to_html(body).lower(),
          "no image unless one is supplied")

    import re as _re

    def visible(markup: str) -> str:
        return _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", markup))

    slug = "ferro-abc"
    check(slug not in visible(shot),
          "with a picture nothing is printed under it")
    check(f'href="https://loom.robindev.org/demo/{slug}"' in shot,
          "the picture itself is the link")
    # A blocked image would otherwise leave the message with nothing to act
    # on at all, so the address has to survive somewhere a reader can see it.
    alt = _re.search(r'alt="([^"]+)"', shot).group(1)
    check(slug in alt,
          "the address rides in the alt text, for a client that blocks images")
    check(slug in visible(out),
          "without a picture the whole address stays, being the only thing to click")


def identity_checks() -> None:
    """The From header, the signature and the demo credit must be one address.

    They were three separate literals in three files. A signature that
    disagrees with the From header above it is a spam signal, and under
    section 17 of the Spam Act it is also a failure to identify the sender
    accurately — which applies to every commercial message regardless of how
    consent was obtained.
    """
    import json
    import pathlib as _pathlib

    from loom.services.email_templates import config
    from loom.services.outreach import _sender

    print("\nsender identity:")
    signature = (config().get("sender") or {}).get("email", "")
    _, from_header = _sender()
    demo = json.loads(_pathlib.Path("config/demo_defaults.json").read_text())
    credit = (demo.get("attribution") or {}).get("email", "")

    check(bool(signature), "the signature carries an address at all")
    check(from_header == signature,
          f"From header matches the signature ({from_header} / {signature})")
    check(credit == signature,
          f"the demo page credit matches too ({credit})")


def consent_checks() -> None:
    """The Schedule 2 cl 4 gate: relevance to the function the address serves.

    Section 22(2) makes the address-harvesting prohibition conditional on the
    messages contravening s16, so everything reduces to consent — and for a
    published business address that means cl 4(2), whose last limb asks
    whether the message is relevant to the role the address represents.

    A careers mailbox is the case that matters. It is conspicuously published,
    it plainly belongs to the business, and a web-development offer is still
    not relevant to it. Publication is not the test.
    """
    from loom.services.consent import best, classify, may_write_to
    from loom.services.email_templates import NoConsentBasisError

    print("\nconsent basis:")
    for address, tier in (
        ("owner@cafe.com.au", "strong"),
        ("manager@cafe.com.au", "strong"),
        ("info@cafe.com.au", "defensible"),
        ("enquiries@cafe.com.au", "defensible"),
        ("bookings@cafe.com.au", "weak"),
        ("careers@cafe.com.au", "refused"),
        ("accounts@cafe.com.au", "refused"),
        ("jo.smith@cafe.com.au", "weak"),
    ):
        check(classify(address)["tier"] == tier, f"{address} -> {tier}")

    check(not may_write_to("careers@x.com")[0], "a careers mailbox is refused")
    check(not may_write_to("jo@x.com")[0],
          "an unexplained personal address is held, not sent")
    check(may_write_to("owner@x.com")[0], "an owner address may be written to")

    # cl 4(2)(d): a refusal on the page removes the exception whatever the role.
    check(not may_write_to("owner@x.com",
                           {"url": "https://x", "refuses_unsolicited": True})[0],
          "a refusal on the page beats even the strongest role")
    check(not may_write_to("owner@x.com", {"url": ""})[0],
          "no provenance means no argument")

    check(best(["careers@x.com", "info@x.com", "owner@x.com"]) == "owner@x.com",
          "the strongest argument is chosen, not the first harvested")
    check(best(["careers@x.com", "accounts@x.com"]) == "",
          "a lead with only refused addresses yields nothing")

    print("\ndrafting refuses what cannot be argued:")

    def drafts(emails: list[str], sources: dict | None = None) -> bool:
        lead = {**LEAD, "emails": emails, "email_sources": sources or {}}
        try:
            render("first_contact", lead, public_base="https://p")
        except NoConsentBasisError:
            return False
        return True

    check(drafts(["owner@x.com"]), "an owner address drafts")
    check(not drafts(["careers@x.com"]), "a careers-only lead never drafts")
    check(not drafts(["bookings@x.com"]), "a bookings-only lead never drafts")
    check(
        not drafts(["owner@x.com"],
                   {"owner@x.com": {"url": "https://x", "refuses_unsolicited": True}}),
        "a page refusal blocks drafting outright",
    )
    lead = {**LEAD, "emails": ["careers@x.com", "owner@x.com"]}
    check(render("first_contact", lead, public_base="https://p")["to"] == "owner@x.com",
          "the recipient is the best-argued address, not emails[0]")


def main() -> int:
    opt_out_checks()
    quoting_checks()
    automated_checks()
    matching_checks()
    gate_checks()
    html_checks()
    identity_checks()
    consent_checks()
    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
