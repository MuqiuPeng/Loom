"""Dynamic emphasis terms — read from profile data, not hardcoded.

BOLD: all skill names from profile (technologies)
ITALIC: company names from experiences + institution names from education
"""


def get_bold_terms(profile_data: dict) -> list[str]:
    """Extract technology names from profile skills for \\textbf{}."""
    terms = set()
    for skill in profile_data.get("skills", []):
        name = skill.get("name", "")
        if name:
            terms.add(name)
    # Sort by length descending — longer phrases first to avoid partial matches
    return sorted(terms, key=len, reverse=True)


def get_italic_terms(profile_data: dict) -> list[str]:
    """Extract company/institution names from profile for \\textit{}."""
    terms = set()
    for exp in profile_data.get("experiences", []):
        company = exp.get("company", "")
        if company:
            terms.add(company)
    for edu in profile_data.get("education", []):
        institution = edu.get("institution", "")
        if institution:
            terms.add(institution)
    return sorted(terms, key=len, reverse=True)
