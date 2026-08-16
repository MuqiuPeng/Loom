"""Render a resume from a caller-supplied template context.

This is the deterministic half of resume production: no Claude calls, no
judgement — Jinja templates in, Markdown/LaTeX/PDF out. It lets an agent
that already did the reasoning (picking bullets, rewriting them, grouping
skills) hand Loom the finished content and get back a stored artifact.

The context shape matches what GenerateResumeStep builds internally, so
both paths render through the same templates.
"""

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import ChainableUndefined, Environment

from loom.current_user import get_current_user
from loom.storage.resume import ResumeArtifact


class _LoudUndefined(ChainableUndefined):
    """Log any template field the caller didn't supply.

    Chainable so `{{ a.b }}` on a missing `a` doesn't explode mid-render —
    templates legitimately probe optional fields with `{%- if x %}`. What
    matters is that the miss is recorded instead of vanishing; the output
    contract then decides whether real content was lost.
    """

    def _fail_with_undefined_error(self, *args, **kwargs):  # noqa: D401
        logger.warning("template referenced undefined field: %s", self._undefined_name)
        return ""

    __str__ = lambda self: ""  # noqa: E731
    __html__ = lambda self: ""  # noqa: E731

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _handle(url: str | None, marker: str) -> str:
    """Username out of a profile URL — 'github.com/foo' -> 'foo'."""
    if not url:
        return ""
    s = url.rstrip("/")
    if marker in s:
        s = s.split(marker, 1)[1]
    else:
        s = s.rsplit("/", 1)[-1]
    return s.strip("/")


def _normalize(ctx: dict) -> dict:
    """Fill in optional keys and derive the fields the templates expect.

    The .tex template needs derived values the .md one doesn't
    (`degree_abbrev`, `linkedin_handle`, `github_handle`). The internal
    pipeline computes those before rendering; external callers shouldn't
    have to know that. Without this, the PDF silently drops the degree
    line and renders a bare 'github.com/' with no username.
    """
    out = dict(ctx)
    out.setdefault("candidate", {})
    out.setdefault("summary", "")
    for key in ("skills", "experiences", "projects", "education", "certifications"):
        out.setdefault(key, [])
    # Templates use `skills` for the grouped list; accept the pipeline's
    # `skill_groups` name too so callers can use either.
    if not out["skills"] and ctx.get("skill_groups"):
        out["skills"] = ctx["skill_groups"]

    cand = dict(out["candidate"])
    if not cand.get("linkedin_handle"):
        cand["linkedin_handle"] = _handle(cand.get("linkedin"), "linkedin.com/in/")
    if not cand.get("github_handle"):
        cand["github_handle"] = _handle(cand.get("github"), "github.com/")
    for field in ("linkedin", "github"):
        url = cand.get(field)
        if url and not url.startswith(("http://", "https://")):
            cand[field] = f"https://{url}"
    out["candidate"] = cand

    for edu in out["education"]:
        if not edu.get("degree_abbrev"):
            degree = (edu.get("degree") or "").strip()
            field = (edu.get("field") or "").strip()
            edu["degree_abbrev"] = f"{degree} ({field})" if (degree and field) else degree

    for exp in out["experiences"]:
        exp.setdefault("bullets", [])
        exp.setdefault("location", "")
    for proj in out["projects"]:
        proj.setdefault("bullets", [])
    return out


def render_resume(ctx: dict, language: str = "en",
                  profile_data: dict | None = None) -> tuple[str, str]:
    """Render (markdown, latex) from a template context."""
    if language not in ("en", "zh"):
        raise ValueError("language must be 'en' or 'zh'")
    ctx = _normalize(ctx)

    md_name = "resume_template_zh.md" if language == "zh" else "resume_template.md"
    tex_name = "resume_template_zh.tex" if language == "zh" else "resume_template.tex"

    # ChainableUndefined, not the default: a template asking for a field the
    # caller didn't send should be visible. Jinja's default silently renders
    # "" — that is how the degree line and the link handles disappeared from
    # every PDF without a single error being raised anywhere.
    content_md = Environment(undefined=_LoudUndefined).from_string(
        _load(md_name)).render(**ctx)

    # Same LaTeX escaping + emphasis rules the pipeline uses
    from loom.steps.generate_resume import make_latex_processor

    tex_env = Environment(undefined=_LoudUndefined)
    tex_env.filters["latex"] = make_latex_processor(profile_data or {})
    content_tex = tex_env.from_string(_load(tex_name)).render(**ctx)

    return content_md, content_tex


def _verify_pdf(pdf_path: str, ctx: dict) -> list[str]:
    """Extract text from the compiled PDF and re-check the output contract.

    Returns a list of problems (empty when clean). Never raises — a broken
    verifier must not take down a render that otherwise succeeded.
    """
    try:
        import pypdf

        from loom.services.render_contract import check_pdf_text, check_residue

        reader = pypdf.PdfReader(pdf_path)
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        if not text.strip():
            return ["pdf produced no extractable text"]
        problems = check_pdf_text(ctx, text) + check_residue("", text)
        if len(reader.pages) > 3:
            problems.append(f"pdf is {len(reader.pages)} pages (expected 1-2)")
        return problems
    except ImportError:
        logger.info("pypdf not installed — skipping PDF contract check")
        return []
    except Exception as e:
        logger.warning("PDF verification failed: %s", e)
        return []


async def render_and_store(
    storage: Any,
    ctx: dict,
    language: str = "en",
    jd_record_id: str | None = None,
    compile_pdf: bool = True,
) -> dict:
    """Render, persist a ResumeArtifact, and (best-effort) compile a PDF.

    Returns {"resume_artifact_id", "pdf_url"|None, "pdf_error"|None}.
    """
    profile = await storage.get_profile(get_current_user())
    profile_data = profile.model_dump(mode="json") if profile else {}

    content_md, content_tex = render_resume(ctx, language, profile_data)

    # Fail loudly if the render dropped or corrupted caller-supplied content,
    # rather than storing a quietly incomplete resume.
    from loom.services.render_contract import assert_contract
    assert_contract(_normalize(ctx), content_md)

    artifact = ResumeArtifact(
        jd_record_id=UUID(jd_record_id) if jd_record_id else None,
        language=language,
        content_md=content_md,
        content_tex=content_tex,
    )
    await storage.save_resume_artifact(artifact)

    result: dict = {"resume_artifact_id": str(artifact.id)}

    if compile_pdf:
        try:
            from loom.services.pdf_generator import PDFGenerator
            pdf_path = await PDFGenerator().generate(content_tex)
            await storage.update_resume_artifact(artifact.id, {"pdf_path": pdf_path})
            from loom.services.signing import resume_pdf_url
            result["pdf_url"] = resume_pdf_url(str(artifact.id))

            # The PDF is the deliverable, and the LaTeX path can lose content
            # the Markdown path keeps (different templates, different fields).
            # Verify the compiled artifact, not just the source.
            warns = _verify_pdf(pdf_path, _normalize(ctx))
            if warns:
                result["pdf_contract_warnings"] = warns
                logger.error("PDF dropped caller content: %s", "; ".join(warns[:8]))
                try:
                    from loom.services.logger import logger as loom_logger
                    await loom_logger.error(
                        "workflow", "resume.render.pdf_contract",
                        f"PDF missing {len(warns)} supplied item(s)",
                        resume_artifact_id=str(artifact.id), missing=warns[:20])
                except Exception:
                    pass
        except Exception as e:
            logger.warning("PDF compilation skipped: %s", e)
            result["pdf_error"] = str(e).split("\n")[0]

    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info(
            "workflow", "resume.render",
            f"Rendered agent-authored resume ({language}, {len(content_md)} chars)",
            resume_artifact_id=str(artifact.id))
    except Exception:
        pass

    return result
