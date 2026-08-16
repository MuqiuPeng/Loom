"""Send yourself one email through the real send path.

Worth having as its own command because the first live send should go to your
own inbox, not a stranger's: it proves the app password, the TLS handshake and
the From header in one go, and a mistake costs nothing.

Uses mailer.send — the same function the approved queue calls — so a pass here
means the queue will work, and a failure here is the failure the queue would
have hit.

    python -m loom.scripts.send_test_email            # renders, then sends
    python -m loom.scripts.send_test_email --dry-run  # renders only
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from loom.services.email_templates import render
from loom.services.mailer import configured, send, transport

load_dotenv()

# A lead shaped exactly like a real one, so the template exercises every slot
# the live path uses.
SAMPLE_LEAD = {
    "id": "test-lead",
    "google_name": "The Test Cafe",
    "site_url": "https://example.com",
    "demo_slug": "the-test-cafe-abc123",
    "demo_public": True,
    "emails": [],
    "audit": {
        "findings": [
            {
                "code": "mobile_broken",
                "weight": 5,
                "label": "Unusable on a phone",
                "detail": "the page is 1208px wide in a 375px window",
            }
        ]
    },
}


async def own_address() -> str:
    """Where to send the test — whichever mailbox is actually in use.

    Read from the transport rather than from GMAIL_ADDRESS, because on the
    Lark path there is no SMTP variable set at all and the script would have
    reported "not set" while the mailbox was working fine.
    """
    if transport() == "lark":
        from loom.services import lark_mail

        try:
            return await lark_mail.address()
        except Exception:
            return ""
    return os.environ.get("SMTP_ADDRESS") or os.environ.get("GMAIL_ADDRESS", "")


async def main() -> int:
    dry_run = "--dry-run" in sys.argv
    address = await own_address()

    draft = render(
        "first_contact",
        SAMPLE_LEAD,
        public_base=os.environ.get("LOOM_PUBLIC_URL", "https://loom.robindev.org"),
    )

    print("=" * 68)
    print(f"To:      {address or '(no mailbox configured)'}")
    print(f"Via:     {transport()}")
    print(f"Subject: [TEST] {draft['subject']}")
    print("=" * 68)
    print(draft["body"])
    print("=" * 68)

    if dry_run:
        print("\ndry run — nothing sent")
        return 0

    if not configured():
        print(
            "\nNot sent: no transport is configured. Either authorise lark-cli\n"
            "(lark-cli auth login --domain mail), or set SMTP_ADDRESS and\n"
            "SMTP_PASSWORD in .env."
        )
        return 1

    try:
        # Marked in the subject so a copy left in the inbox is never mistaken
        # for something that went to a real business.
        await send(address, f"[TEST] {draft['subject']}", draft["body"])
    except Exception as e:
        print(f"\nSend failed: {e}")
        return 1

    print(f"\nSent to {address}. Check the inbox — and the spam folder.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
