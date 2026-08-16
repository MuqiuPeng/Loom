"""Decide, per address, whether inferred consent can be argued for it.

The Spam Act does not forbid writing to a published business address, and it
does not forbid finding that address with a crawler. Section 22(2) says in
terms that the prohibition on using address-harvesting software "does not
apply … if the use was not in connection with sending commercial electronic
messages in contravention of section 16" — so the harvesting question is
derivative of the consent question, not a separate offence.

Everything therefore turns on Schedule 2 clause 4. Publication alone is
explicitly NOT enough: cl 4(1) says consent "may not be inferred from the mere
fact that the … address has been published". The exception in cl 4(2) applies
only where the address reaches a person in a work role, was conspicuously
published, appears to have been published with agreement, carries no statement
refusing unsolicited commercial messages — and, the part this module exists
for, where the message is

    relevant to … the work-related business, functions or duties of the
    employee, director, officer, partner, office-holder or self-employed
    individual concerned … or … the function or role concerned.

That last limb is a question about a particular address, not about the
business. A website-redesign offer is plainly relevant to whoever handles the
business's general enquiries. It is not relevant to the address a café
publishes for job applications, however public that address is.

Section 16(5) puts the evidential burden on the sender, and ACMA's Victorian
Institute of Technology investigation turned on exactly that: the sender had
to point to evidence that ALL elements of the exception were met, and could
not. So the verdict and its reasoning are recorded per address at the moment
of collection, alongside where it was found.

Nothing here is legal advice and nothing here is a substitute for it. What it
does is make the argument explicit and refusable, so a lead that cannot be
defended is not sent to.
"""

import re

# Order is protective, not alphabetical: every refused role is tested before
# any sendable one. Otherwise relaxing a stem so "enquiries" matches "enquir"
# also lets "hiring" match "hi", and a recruitment address would be classified
# as general enquiries — a wrong verdict in the one direction that matters.
_ROLES: list[tuple[str, re.Pattern, str, str]] = [
    (
        "recruitment",
        re.compile(r"^(career|job|hr|recruit|hiring|apply|applicant|application)", re.I),
        "refused",
        "published for job applications. A commercial offer of web "
        "development is not relevant to that function, so the conspicuous "
        "publication exception cannot be argued for this address",
    ),
    (
        "accounts",
        re.compile(r"^(account|billing|invoice|payment|finance|payable)|^(ap|ar)\b", re.I),
        "refused",
        "published for invoicing and payments; a sales approach is not "
        "relevant to that function",
    ),
    (
        "unattended",
        re.compile(r"(no-?reply|do-?not-?reply|mailer-daemon|bounce)", re.I),
        "refused",
        "not read by a person",
    ),
    (
        "abuse",
        re.compile(r"^(abuse|postmaster|spam|security|privacy|legal|complaint)", re.I),
        "refused",
        "published to receive complaints about unsolicited mail, among other "
        "things — writing a sales approach to it is the opposite of what it "
        "is for",
    ),
    (
        "bookings",
        re.compile(r"^(booking|reservation|reserve|table|order)", re.I),
        "weak",
        "published for customers making bookings, not for business "
        "correspondence — relevance to a web-development offer is arguable "
        "at best",
    ),
    (
        "events",
        re.compile(r"^(event|function|catering|private|wedding|party)", re.I),
        "weak",
        "published for event enquiries from customers; a web-development "
        "offer is not relevant to that function",
    ),
    (
        "owner",
        re.compile(r"^(owner|founder|director|principal|proprietor)", re.I),
        "strong",
        "the address the business publishes for its owner, whose "
        "work-related business plainly includes how the business presents "
        "itself online",
    ),
    (
        "manager",
        re.compile(r"^(manager|management|gm|operations|ops)\b", re.I),
        "strong",
        "the address published for whoever runs the business day to day, "
        "whose duties include its web presence",
    ),
    (
        "marketing",
        re.compile(r"^(marketing|media|press|brand|webmaster|web|digital)", re.I),
        "defensible",
        "the address published for the function that would itself own the "
        "website, making a message about the website directly relevant",
    ),
    (
        "general enquiries",
        re.compile(r"^(info|hello|hey|hi|contact|enquir|inquir|admin|office|mail|team|shop|studio)", re.I),
        "defensible",
        "the address the business publishes for general business enquiries, "
        "which is the function a message about its own website addresses",
    ),
]

# Tiers that may be written to. "weak" is excluded deliberately: an argument
# that is merely arguable is not one to build a sending pipeline on, and the
# cost of excluding it is a handful of leads.
SENDABLE = ("strong", "defensible")


def classify(address: str) -> dict[str, str]:
    """The role an address represents, and whether the offer is relevant to it.

    Returns role, tier and reason. `reason` is written to be read by a person
    asking why this particular address was written to — it is the sentence
    that has to survive the question, so it says what the address is for
    rather than restating that it was public.
    """
    local = (address or "").split("@", 1)[0].strip().lower()
    if not local:
        return {
            "role": "unknown",
            "tier": "refused",
            "reason": "not an address",
        }

    for role, pattern, tier, reason in _ROLES:
        if pattern.search(local):
            return {"role": role, "tier": tier, "reason": reason}

    # A personal address — jo@, sarah.smith@ — reaches an individual whose
    # role is not stated anywhere. cl 4(2) needs the message to be relevant to
    # that person's work-related duties, and nothing here establishes what
    # those are. Not refused outright, because at a two-person café the
    # owner's first name IS the business contact; but not sendable without
    # someone saying so.
    return {
        "role": "named individual",
        "tier": "weak",
        "reason": (
            "reaches a named person whose role the site does not state, so "
            "there is nothing to show a web-development offer is relevant to "
            "their work-related duties"
        ),
    }


def may_write_to(address: str, source: dict | None = None) -> tuple[bool, str]:
    """Whether this address can be written to, and why not if it cannot.

    `source` is the provenance record captured at collection time. A page that
    refused unsolicited commercial mail removes the exception outright,
    whatever the role — cl 4(2)(d) is a condition, not a factor to weigh.
    """
    if source and source.get("refuses_unsolicited"):
        return False, (
            "the page publishing this address refused unsolicited commercial "
            "email, which removes the conspicuous publication exception"
        )
    if source and not source.get("url"):
        return False, (
            "no record of where this address was published, so the exception "
            "cannot be argued for it"
        )

    verdict = classify(address)
    if verdict["tier"] in SENDABLE:
        return True, verdict["reason"]
    return False, f"{verdict['role']}: {verdict['reason']}"


def best(addresses: list[str], sources: dict | None = None) -> str:
    """The address with the strongest argument, or "" if none can be argued.

    Preferring the owner over a generic mailbox is not only a legal
    improvement — it is the difference between reaching the person who decides
    and reaching whoever empties the info@ inbox.
    """
    ranked: list[tuple[int, str]] = []
    for address in addresses or []:
        allowed, _ = may_write_to(address, (sources or {}).get(address.lower()))
        if not allowed:
            continue
        tier = classify(address)["tier"]
        ranked.append((SENDABLE.index(tier), address))
    if not ranked:
        return ""
    ranked.sort()
    return ranked[0][1]
