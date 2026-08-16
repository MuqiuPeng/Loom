"""Signed-URL helpers for auth-free resource links (e.g. resume PDFs in Notion)."""

import hashlib
import hmac
import os


def resume_pdf_sig(resume_id: str) -> str:
    """Deterministic per-artifact signature derived from LOOM_API_KEY."""
    key = os.environ.get("LOOM_API_KEY", "")
    return hmac.new(key.encode(), f"resume-pdf:{resume_id}".encode(),
                    hashlib.sha256).hexdigest()[:20]


def resume_pdf_url(resume_id: str) -> str:
    base = os.environ.get("LOOM_PUBLIC_API_URL", "https://loom-api.robindev.org")
    return f"{base}/api/resumes/{resume_id}/pdf?sig={resume_pdf_sig(resume_id)}"
