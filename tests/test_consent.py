"""The gate that decides whether a commercial email may lawfully be sent.

This module had no tests at all, and the omission had already cost something:
`may_write_to` refused a provenance record with a missing url and allowed an
address with no record whatsoever, which is the burden in s16(5) applied
backwards. Nothing caught it because nothing looked. Every case below is a
verdict somebody could be held to.
"""

import pytest

from loom.services import consent
from loom.services.company_scout import _clean_emails
from loom.services.email_templates import NoConsentBasisError, render

GOOD = {"url": "https://cafe.test/contact", "how": "mailto link",
        "refuses_unsolicited": False}


# ── the evidential burden ────────────────────────────────────────────

def test_no_provenance_at_all_is_refused():
    """Absence of evidence cannot be the one input that passes.

    s16(5) puts the burden on the sender. An address nobody recorded finding
    might have come off a published contact page or out of an unfilled
    template, and that difference is the entire argument.
    """
    allowed, why = consent.may_write_to("info@cafe.test", None)
    assert not allowed
    assert "nothing records where this address was published" in why


def test_provenance_missing_its_url_is_refused():
    allowed, why = consent.may_write_to("info@cafe.test", {"how": "page text"})
    assert not allowed
    assert "no record of where this address was published" in why


def test_page_refusing_unsolicited_mail_beats_a_sendable_role():
    """cl 4(2)(d) is a condition, not a factor to weigh against the role."""
    allowed, why = consent.may_write_to(
        "info@cafe.test", {**GOOD, "refuses_unsolicited": True}
    )
    assert not allowed
    assert "refused unsolicited commercial" in why


def test_published_general_enquiries_address_is_sendable():
    allowed, _ = consent.may_write_to("info@cafe.test", GOOD)
    assert allowed


# ── relevance to the function the address serves ─────────────────────

@pytest.mark.parametrize("address", [
    "careers@cafe.test", "jobs@cafe.test", "hr@cafe.test",
    "recruitment@cafe.test", "accounts@cafe.test", "invoices@cafe.test",
])
def test_roles_a_web_offer_is_not_relevant_to_are_refused(address):
    """Conspicuous publication is not enough — cl 4(2) needs relevance."""
    allowed, _ = consent.may_write_to(address, GOOD)
    assert not allowed, f"{address} should not be sendable"


def test_hiring_is_not_read_as_general_enquiries():
    """The stem-ordering hazard the role table is written to avoid.

    Relax "enquiries" far enough and "hiring" matches "hi" — a recruitment
    address classified as general enquiries, wrong in the only direction that
    matters.
    """
    assert consent.classify("hiring@cafe.test")["role"] == "recruitment"
    assert consent.classify("hi@cafe.test")["role"] == "general enquiries"


# ── which address gets written to ────────────────────────────────────

def test_best_prefers_the_owner_over_the_generic_mailbox():
    sources = {"info@cafe.test": GOOD, "owner@cafe.test": GOOD}
    assert consent.best(["info@cafe.test", "owner@cafe.test"], sources) \
        == "owner@cafe.test"


def test_best_returns_nothing_when_every_address_is_refused():
    assert consent.best(["careers@cafe.test"], {"careers@cafe.test": GOOD}) == ""


def test_best_skips_addresses_with_no_provenance():
    """One documented address beats two, one of which nobody can vouch for."""
    sources = {"info@cafe.test": GOOD}
    assert consent.best(["owner@cafe.test", "info@cafe.test"], sources) \
        == "info@cafe.test"


# ── template placeholders never reach the gate ───────────────────────

@pytest.mark.parametrize("address", [
    "hi@mystore.com",        # Square's own template default
    "you@yourdomain.com",
    "hello@yoursite.com",
    "info@example.com",
])
def test_template_placeholders_are_dropped_before_consent_sees_them(address):
    """hi@mystore.com reached the send path on a live lead.

    A real domain, a plausible local part, and a role the classifier reads as
    general enquiries — nothing downstream was going to stop it.
    """
    assert _clean_emails([address]) == []


def test_a_real_address_at_a_normal_domain_survives_cleaning():
    assert _clean_emails(["info@cafecalibre.com.au"]) == ["info@cafecalibre.com.au"]


# ── what a person reads when it refuses ──────────────────────────────

def _lead(**over):
    return {
        "google_name": "Café Test", "site_url": "https://cafe.test",
        "demo_slug": "abc", "demo_public": True,
        "audit": {"findings": [{"code": "no_https", "label": "No HTTPS",
                                "detail": "served over http", "weight": 5}]},
        **over,
    }


def test_no_address_found_says_so_without_a_stray_colon():
    """"(no address): unknown: not an address" read as a bug, not an answer."""
    with pytest.raises(NoConsentBasisError) as e:
        render("first_contact", _lead(emails=[]), public_base="https://x.test")
    assert str(e.value).startswith("no email address was found")


def test_refusal_names_every_address_and_why_each_failed():
    lead = _lead(emails=["careers@cafe.test"],
                 email_sources={"careers@cafe.test": GOOD})
    with pytest.raises(NoConsentBasisError) as e:
        render("first_contact", lead, public_base="https://x.test")
    assert "careers@cafe.test — recruitment" in str(e.value)


def test_a_lead_with_no_provenance_is_refused_at_draft_time():
    """The two leads one click from being sent to, before this landed."""
    lead = _lead(emails=["info@cafe.test"])
    with pytest.raises(NoConsentBasisError) as e:
        render("first_contact", lead, public_base="https://x.test")
    assert "harvest the site again" in str(e.value)
