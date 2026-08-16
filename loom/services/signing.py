"""Signed-URL helpers for auth-free resource links (e.g. resume PDFs in Notion).

These signatures have a different lifetime from the API key. A signed link is
published — it goes into a Notion row and stays there — while the API key is a
credential that should be rotatable at any time, ideally without a second
thought. Deriving one from the other coupled them: rotating the key silently
invalidated every link already handed out, which turns a routine rotation into
an outage, which is how keys end up not being rotated.

So the signing secret is its own value. Rotate it deliberately, when you want
every outstanding link to stop working.
"""

import hashlib
import hmac
import os


class SigningNotConfigured(RuntimeError):
    """Raised when LOOM_SIGNING_SECRET is missing.

    Deliberately not falling back to LOOM_API_KEY: that fallback is exactly
    the coupling this module exists to undo, and a silent one would restore it
    the first time someone deployed without the variable set.
    """


def _secret() -> str:
    secret = os.environ.get("LOOM_SIGNING_SECRET", "")
    if not secret:
        raise SigningNotConfigured(
            "LOOM_SIGNING_SECRET is not set. Generate one "
            "(`python -c 'import secrets;print(secrets.token_urlsafe(32))'`), "
            "put it in .env, and restart. Changing it invalidates every "
            "signed link already published."
        )
    return secret


def resume_pdf_sig(resume_id: str) -> str:
    """Deterministic per-artifact signature."""
    return hmac.new(
        _secret().encode(), f"resume-pdf:{resume_id}".encode(), hashlib.sha256
    ).hexdigest()[:20]


def resume_pdf_url(resume_id: str) -> str:
    base = os.environ.get("LOOM_PUBLIC_API_URL", "https://loom-api.robindev.org")
    return f"{base}/api/resumes/{resume_id}/pdf?sig={resume_pdf_sig(resume_id)}"
