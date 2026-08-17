"""Regression check for the resume templates.

Run after ANY template edit. Renders a fixed golden sample through every
template (en/zh × md/tex) and asserts the output contract — the same
contract the live render path enforces.

This exists because a template edit can silently delete a whole section:
moving Education past \\end{document} produced a PDF that compiled
cleanly, returned ok from the API, and wrote back to Notion, while the
degree and certifications were simply gone.

    python -m loom.scripts.check_templates

Exits non-zero on any violation, so it can gate a commit.
"""

import sys

from loom.services.render_contract import ContractError, assert_contract
from loom.services.resume_render import render_resume

GOLDEN = {
    "candidate": {
        "name": "Test Candidate",
        "email": "test@example.com",
        "phone": "0400000000",
        "location": "Sydney",
        "github": "github.com/testuser",
        "linkedin": "www.linkedin.com/in/test-user",
    },
    "summary": "Backend engineer with a data background.",
    "skills": [
        {"category": "Backend", "content": "Python, FastAPI — REST services"},
        {"category": "Data", "content": "PostgreSQL, pandas — analysis pipelines"},
    ],
    "experiences": [
        {
            "title": "Senior Engineer",
            "company": "Acme Corp",
            "location": "Sydney, Australia",
            "period": "03/2026 -- Present",
            "bullets": [
                "Built the billing service with **FastAPI** on PostgreSQL.",
                "Reduced report generation time through query optimisation.",
            ],
        },
        {
            "title": "Engineer",
            "company": "Beta Ltd",
            "location": "Shanghai, China",
            "period": "01/2023 -- 02/2026",
            "bullets": ["Maintained the data ingestion pipeline."],
        },
    ],
    "projects": [
        {"name": "Sample Project", "bullets": ["Built a thing that does something useful."]},
    ],
    "education": [
        {
            "institution": "Example University",
            "degree": "Master of Computer Science",
            "field": "Machine Learning",
            "period": "02/2024 -- 12/2025",
        },
    ],
    "certifications": [{"name": "AWS Certified Developer - Associate", "year": "2025"}],
}

# Section order the templates must produce — strongest content first
EXPECTED_ORDER_EN = ["Technical Skills", "Experience", "Projects", "Education", "Certifications"]
EXPECTED_ORDER_ZH = ["专业技能", "工作经历", "项目经历", "教育背景", "证书与奖项"]


def _check_order(text: str, expected: list[str], label: str) -> list[str]:
    positions = []
    for section in expected:
        i = text.find(section)
        if i < 0:
            return [f"{label}: section {section!r} missing entirely"]
        positions.append((i, section))
    actual = [s for _, s in sorted(positions)]
    if actual != expected:
        return [f"{label}: section order is {actual}, expected {expected}"]
    return []


def main() -> int:
    problems: list[str] = []

    for language, expected in (("en", EXPECTED_ORDER_EN), ("zh", EXPECTED_ORDER_ZH)):
        try:
            content_md, content_tex = render_resume(GOLDEN, language, {})
        except Exception as e:
            problems.append(f"{language}: render raised {type(e).__name__}: {e}")
            continue

        for body, kind in ((content_md, "md"), (content_tex, "tex")):
            try:
                # LaTeX legitimately contains backslash commands; check the
                # contract on content presence for both, residue only on md.
                assert_contract(GOLDEN, body if kind == "md" else content_md)
                if kind == "tex":
                    from loom.services.render_contract import check_pdf_text
                    missing = check_pdf_text(GOLDEN, body)
                    if missing:
                        problems += [f"{language}.tex missing {m}" for m in missing]
            except ContractError as e:
                problems.append(f"{language}.{kind}: {e}")

            problems += _check_order(body, expected, f"{language}.{kind}")

        # \end{document} must come after every section
        end = content_tex.rfind("\\end{document}")
        if end < 0:
            problems.append(f"{language}.tex: no \\end{{document}}")
        else:
            after = content_tex[end:]
            for section in expected:
                if section in after:
                    problems.append(
                        f"{language}.tex: section {section!r} appears AFTER "
                        "\\end{document} — LaTeX will silently drop it")

    if problems:
        print(f"TEMPLATE CHECK FAILED — {len(problems)} problem(s):\n")
        for p in problems:
            print(f"  ✗ {p}")
        return 1

    print("TEMPLATE CHECK PASSED — en/zh × md/tex: content intact, section order correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
