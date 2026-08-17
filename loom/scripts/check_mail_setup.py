"""Check that a sending domain is actually configured to send.

Run this after adding DNS records and before the first real send.

    python -m loom.scripts.check_mail_setup              # reads SMTP_ADDRESS
    python -m loom.scripts.check_mail_setup robindev.org

What it cannot tell you, and this is the important caveat: DNS can be
perfect while every message still fails DMARC. Alignment is decided by the
envelope, not the zone — relaying a From: @yourdomain through consumer Gmail
authenticates gmail.com and signs d=gmail.com, neither of which aligns, and no
record here would reveal that. The only check that catches it is sending to
your own inbox and reading the Authentication-Results header, which is what
send_test_email is for. This script is the cheap half.
"""

import asyncio
import sys

import httpx

from loom.services.dns_check import DOH_URL, TIMEOUT

TYPE_TXT = 16
TYPE_MX = 15

# Every host in the running, verified against what each actually publishes.
KNOWN_SPF = {
    "_spf.google.com": "Google Workspace",
    "spf.onlarksuite.com": "Lark Mail",
    "spf.migadu.com": "Migadu",
    "_spf.purelymail.com": "Purelymail",
    "spf.messagingengine.com": "Fastmail",
    "zoho.com": "Zoho",
}

problems: list[str] = []
notes: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"  \033[32mok\033[0m    {label}" + (f" — {detail}" if detail else ""))


def bad(label: str, detail: str) -> None:
    print(f"  \033[31mFAIL\033[0m  {label} — {detail}")
    problems.append(label)


def warn(label: str, detail: str) -> None:
    print(f"  \033[33mnote\033[0m  {label} — {detail}")
    notes.append(label)


async def records(client: httpx.AsyncClient, name: str, rtype: int) -> list[str]:
    try:
        response = await client.get(
            DOH_URL, params={"name": name, "type": rtype}, timeout=TIMEOUT
        )
        body = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    return [
        entry.get("data", "").strip('"')
        for entry in (body.get("Answer") or [])
        if entry.get("type") == rtype
    ]


async def check(domain: str) -> None:
    print(f"\nsending domain: {domain}\n")
    async with httpx.AsyncClient() as client:
        mx = await records(client, domain, TYPE_MX)
        if mx:
            ok("MX", ", ".join(sorted(mx)))
        else:
            bad("MX", "no mail exchanger — the domain cannot receive replies, "
                      "and the Spam Act needs a working opt-out address")

        txt = await records(client, domain, TYPE_TXT)
        spf = [t for t in txt if t.lower().startswith("v=spf1")]
        if not spf:
            bad("SPF", "no v=spf1 record")
        elif len(spf) > 1:
            bad("SPF", f"{len(spf)} records — more than one is a permerror, "
                       "and permerror is treated as no SPF at all")
        else:
            value = spf[0]
            host = next((h for h in KNOWN_SPF if h in value), "")
            ok("SPF", f"{value}" + (f"   [{KNOWN_SPF[host]}]" if host else ""))
            if not host:
                warn("SPF", "no known mail host in the include — check this "
                            "matches whoever actually sends your mail")
            # -all is correct with a single sender and is what Lark itself
            # specifies. It only bites once a second sending path exists, so
            # warn on that combination rather than on -all alone.
            if value.rstrip().endswith("-all") and value.lower().count("include:") > 1:
                warn("SPF", f"-all with {value.lower().count('include:')} includes "
                            "— every sender must be in one of them or it is "
                            "hard-rejected")

        dmarc = [
            t for t in await records(client, f"_dmarc.{domain}", TYPE_TXT)
            if t.lower().startswith("v=dmarc1")
        ]
        if not dmarc:
            bad("DMARC", "no record — and without rua= you get no reports, "
                         "which at this volume is the ONLY deliverability "
                         "feedback available to you")
        else:
            value = dmarc[0]
            ok("DMARC", value)
            if "rua=" not in value.lower():
                bad("DMARC", "no rua= — aggregate reports are the one feedback "
                             "channel that works below Postmaster Tools' volume "
                             "floor. Without it you are sending blind.")

        # DKIM lives at a selector the host chooses, so it can only be probed.
        found = []
        for selector in ("google", "key1", "default", "dkim", "fm1", "mail",
                         "purelymail1", "zoho", "s1"):
            got = await records(client, f"{selector}._domainkey.{domain}", TYPE_TXT)
            if any("v=dkim1" in g.lower() or "p=" in g for g in got):
                found.append(selector)
        if found:
            ok("DKIM", f"published at {', '.join(s + '._domainkey' for s in found)}")
        else:
            warn("DKIM", "none found at the usual selectors. It may be at one "
                         "this script doesn't guess — confirm in your host's "
                         "admin panel that DKIM is switched ON, which for "
                         "Google Workspace it is NOT by default")


def main() -> int:
    domain = ""
    if len(sys.argv) > 1:
        domain = sys.argv[1]
    else:
        from dotenv import load_dotenv

        load_dotenv()
        from loom.services.mailer import _credentials

        address, _ = _credentials()
        domain = address.rsplit("@", 1)[-1] if "@" in address else ""

    if not domain:
        print("no domain — pass one, or set SMTP_ADDRESS in .env")
        return 1
    if domain in ("gmail.com", "googlemail.com"):
        print(f"\nsending domain: {domain}\n")
        ok("gmail.com is authenticated by Google", "nothing to configure")
        warn("no telemetry", "Postmaster Tools and DMARC reports need a domain "
                             "you control — on gmail.com you are sending blind")
        return 0

    asyncio.run(check(domain))

    print()
    if problems:
        print(f"{len(problems)} problem(s): {', '.join(problems)}")
        print("Fix these before the first send.")
        return 1
    print("DNS looks right.")
    print("Now prove alignment: python -m loom.scripts.send_test_email")
    print("then open the message source and read Authentication-Results —")
    print(f"both spf= and dkim= must say {domain}, not your relay's domain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
