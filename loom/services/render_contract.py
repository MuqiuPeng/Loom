"""Output contract for rendered resumes.

The failure mode this exists to catch: the pipeline reports success at
every step, LaTeX compiles, the API returns ok — and the PDF is silently
missing a section. Jinja renders an undefined variable as "" without
complaining, so a template that asks for a field the caller didn't send
loses that content with no error anywhere.

The guard is to verify the OUTPUT contains what the INPUT promised,
rather than trusting that no step raised. Checks are deterministic and
run on every render; a violation fails the render loudly.
"""

import re
from typing import Any

# Markers that mean a template or upstream step leaked through
RESIDUE_PATTERNS: list[tuple[str, str]] = [
    (r"\{\{|\}\}", "Jinja placeholder"),
    (r"\{%", "Jinja statement"),
    (r"\\[a-zA-Z]+\{", "LaTeX command"),
    (r"\bNone\b|\bundefined\b|\bnan\b", "null value rendered as text"),
]


class ContractViolation(Exception):
    """Rendered output is missing content the caller supplied."""


def _flat(s: str) -> str:
    """Normalise for comparison across all three representations.

    The same bullet appears as `**x**` in Markdown, `\\textbf{x}` in LaTeX,
    and plain `x` in extracted PDF text, so emphasis must be stripped from
    whichever form is being compared. Whitespace is collapsed because PDF
    extraction inserts breaks mid-word ("F astAPI"), and case is folded.
    """
    s = s or ""
    # Typography: LaTeX turns straight quotes into curly ones and -- into an
    # en dash, so the same sentence differs between what the caller sent and
    # what the PDF contains. Fold both to a canonical form.
    for fancy, plain in (
        ("\u2018", "'"), ("\u2019", "'"), ("\u201b", "'"),      # single quotes
        ("\u201c", '"'), ("\u201d", '"'), ("\u201e", '"'),      # double quotes
        ("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"),      # en/em dash, minus
        ("\u2026", "..."), ("\u00a0", " "),                      # ellipsis, nbsp
    ):
        s = s.replace(fancy, plain)
    s = re.sub(r"-{2,}", "-", s)
    # LaTeX emphasis wrappers: keep the argument, drop the command
    s = re.sub(r"\\(?:textbf|textit|emph|texttt|underline)\s*\{([^{}]*)\}", r"\1", s)
    # Bare LaTeX commands (\item, \hfill, ...) and stray braces
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "")
    # Markdown emphasis
    s = re.sub(r"\*\*|\*|`|_", "", s)
    return re.sub(r"\s+", "", s).lower()


def _present(needle: str, haystack_flat: str) -> bool:
    n = _flat(needle)
    return bool(n) and n in haystack_flat


def check_markdown(ctx: dict, content_md: str) -> list[str]:
    """Every non-empty value the caller supplied must survive into the output.

    Markdown is checked rather than the PDF because it is the faithful
    text form; the LaTeX path is verified separately against the same
    expectations by check_pdf_text.
    """
    return _check_text(ctx, content_md, "markdown")


def check_pdf_text(ctx: dict, pdf_text: str) -> list[str]:
    return _check_text(ctx, pdf_text, "pdf")


def _check_text(ctx: dict, text: str, label: str) -> list[str]:
    flat = _flat(text)
    missing: list[str] = []

    def expect(value: Any, what: str) -> None:
        if isinstance(value, str) and value.strip() and not _present(value, flat):
            missing.append(f"{what}: {value[:70]!r}")

    cand = ctx.get("candidate") or {}
    for key in ("name", "email", "phone", "location"):
        expect(cand.get(key), f"candidate.{key}")
    # Links render as handles, so assert on the handle rather than the URL
    for key, marker in (("linkedin", "linkedin.com/in/"), ("github", "github.com/")):
        url = cand.get(key)
        if url:
            handle = url.rstrip("/").split(marker)[-1].rsplit("/", 1)[-1]
            expect(handle, f"candidate.{key} handle")

    for i, exp in enumerate(ctx.get("experiences") or []):
        expect(exp.get("company"), f"experiences[{i}].company")
        expect(exp.get("title"), f"experiences[{i}].title")
        expect(exp.get("location"), f"experiences[{i}].location")
        for b in exp.get("bullets") or []:
            # Compare a prefix: templates may truncate or wrap, but the
            # opening clause of a supplied bullet must appear verbatim.
            if b.strip() and not _present(b[:60], flat):
                missing.append(f"experiences[{i}] bullet: {b[:60]!r}")

    for i, proj in enumerate(ctx.get("projects") or []):
        expect(proj.get("name"), f"projects[{i}].name")

    for i, edu in enumerate(ctx.get("education") or []):
        expect(edu.get("institution"), f"education[{i}].institution")
        expect(edu.get("degree"), f"education[{i}].degree")

    for i, cert in enumerate(ctx.get("certifications") or []):
        expect(cert.get("name"), f"certifications[{i}].name")

    for i, grp in enumerate(ctx.get("skills") or []):
        expect(grp.get("category"), f"skills[{i}].category")

    return missing


def check_residue(content_md: str, pdf_text: str | None = None) -> list[str]:
    """Template leakage that should never reach a rendered resume."""
    found: list[str] = []
    for body, where in ((content_md, "markdown"), (pdf_text, "pdf")):
        if not body:
            continue
        for pat, label in RESIDUE_PATTERNS:
            # LaTeX commands are expected in .tex, never in md or extracted text
            if label == "LaTeX command" and where == "markdown":
                if re.search(r"\\(textbf|hfill|section|item|href|begin|end)\b", body):
                    found.append(f"{where}: {label}")
                continue
            m = re.search(pat, body)
            if m:
                found.append(f"{where}: {label} ({m.group(0)[:20]!r})")
    return found


def assert_contract(ctx: dict, content_md: str, pdf_text: str | None = None) -> None:
    """Raise if rendered output lost or corrupted caller-supplied content."""
    problems = check_markdown(ctx, content_md)
    if pdf_text:
        pdf_missing = check_pdf_text(ctx, pdf_text)
        problems += [f"[pdf] {p}" for p in pdf_missing if p not in problems]
    problems += check_residue(content_md, pdf_text)
    if problems:
        raise ContractViolation(
            f"{len(problems)} item(s) supplied by the caller did not survive rendering: "
            + "; ".join(problems[:12])
            + (f" … +{len(problems) - 12} more" if len(problems) > 12 else "")
        )
