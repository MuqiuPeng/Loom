"""Build a profile-derived generic JD for no-JD resume generation.

Instead of special-casing every pipeline step for a "no JD" mode, we
synthesize a JDRecord from the user's own profile (summary + skills +
most recent title). The existing match/select/generate pipeline then
runs unchanged against this generic target.
"""

import re
from typing import Any

from loom.storage.resume import JDRecord

GENERIC_COMPANY = "General"

# Skill levels ordered by seniority for required/preferred split
_LEVEL_RANK = {"expert": 0, "proficient": 1, "familiar": 2}


def _default_title(profile: Any, focus: str | None, lang: str = "en") -> str:
    if focus:
        return focus
    if lang == "zh":
        summary = (getattr(profile, "summary_zh", None) or "").strip()
        if summary:
            # First clause of the zh summary is the positioning statement,
            # e.g. "以后端为核心的软件工程师，具有..."
            head = re.split(r"[，。,.]", summary)[0].strip()
            if head:
                return head
        return "软件工程师"
    summary = (getattr(profile, "summary_en", None) or "").strip()
    # First clause of the summary is the positioning statement,
    # e.g. "Backend-focused software engineer with ..."
    if summary:
        head = summary.split(".")[0]
        if " with " in head:
            head = head.split(" with ")[0]
        title = head.strip().rstrip(",")
        if title:
            return title[0].upper() + title[1:]
    return "Software Engineer"


def build_generic_jd(profile: Any, skills: list[Any], focus: str | None = None,
                     lang: str = "en") -> dict[str, Any]:
    """Derive generic JD fields from the profile.

    Returns a dict with title / raw_text / required_skills /
    preferred_skills / key_requirements. The raw_text is written in
    `lang` so downstream steps see a target in the resume's language.
    """
    ranked = sorted(skills, key=lambda s: _LEVEL_RANK.get(getattr(s, "level", "familiar"), 3))
    required = [s.name for s in ranked if getattr(s, "level", "") in ("expert", "proficient")][:12]
    preferred = [s.name for s in ranked if getattr(s, "level", "") == "familiar"][:8]

    title = _default_title(profile, focus, lang)

    if lang == "zh":
        summary = (getattr(profile, "summary_zh", None)
                   or getattr(profile, "summary_en", None) or "").strip()
        key_requirements = [
            "展示最强、最具代表性的职业成就",
            "体现跨岗位的职责演进与技术深度",
            "突出可量化的业务与工程影响",
        ]
        raw_text = (
            "[通用目标——由个人档案生成，非真实招聘启事]\n\n"
            f"目标定位：{title}\n\n"
            f"候选人概述：\n{summary}\n\n"
            f"需重点展示的核心技能：{'、'.join(required)}\n"
            f"辅助技能：{'、'.join(preferred)}\n\n"
            "目标：生成一份通用简历，呈现候选人最强、最具代表性的工作成果，"
            "而非针对某个具体职位定制。"
        )
    else:
        summary = (getattr(profile, "summary_en", None) or "").strip()
        key_requirements = [
            "Demonstrate strongest and most representative professional achievements",
            "Show progression of responsibility and technical depth across roles",
            "Highlight quantified business and engineering impact",
        ]
        raw_text = (
            f"[Generic target — derived from profile, not a real job posting]\n\n"
            f"Target positioning: {title}\n\n"
            f"Candidate summary:\n{summary}\n\n"
            f"Core skills to showcase: {', '.join(required)}\n"
            f"Supporting skills: {', '.join(preferred)}\n\n"
            "Goal: a general-purpose resume presenting the candidate's strongest, "
            "most representative work — not tailored to any specific vacancy."
        )

    return {
        "title": title,
        "raw_text": raw_text,
        "required_skills": required,
        "preferred_skills": preferred,
        "key_requirements": key_requirements,
    }


async def upsert_generic_jd(storage: Any, user_id: str, focus: str | None = None,
                            lang: str = "en") -> JDRecord:
    """Create or refresh the generic JDRecord for this user.

    Reuses the existing record with company == GENERIC_COMPANY and the
    same title so the jobs list doesn't accumulate duplicates; skills
    are refreshed from the current profile on every call.
    """
    profile = await storage.get_profile(user_id)
    if not profile:
        raise ValueError("No profile found — set up your profile first")
    skills = await storage.get_skills(profile.id)

    fields = build_generic_jd(profile, skills, focus, lang)

    existing = await storage.list_jd_records(user_id)
    for jd in existing:
        if jd.company == GENERIC_COMPANY and jd.title == fields["title"]:
            updated = await storage.update_jd_record(jd.id, fields)
            return updated or jd

    record = JDRecord(company=GENERIC_COMPANY, user_id=user_id, **fields)
    await storage.save_jd_record(record)
    return record
