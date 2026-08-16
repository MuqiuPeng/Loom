"""PostgreSQL implementation of DataStorage.

Uses SQLAlchemy 2.0 async for database operations.
Implements the same interface as InMemoryDataStorage.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID


def _parse_date_str(s: str | None) -> date | None:
    """Parse YYYY-MM or YYYY-MM-DD string to date."""
    if not s:
        return None
    try:
        parts = s.split("-")
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        return date.fromisoformat(s)
    except (ValueError, IndexError):
        return None

from sqlalchemy import delete, func, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from loom.current_user import get_current_user
from loom.storage.bullet import Bullet, BulletType, Confidence
from loom.storage.database import get_session
from loom.storage.models import (
    BulletModel,
    EducationModel,
    ExperienceModel,
    JDRecordModel,
    LogEntryModel,
    ProfileModel,
    ProjectModel,
    ResumeArtifactModel,
    SkillModel,
    TaskModel,
    TokenUsageModel,
)
from loom.storage.profile import Education, Experience, Profile, Skill, SkillLevel
from loom.storage.project import Project
from loom.storage.repository import DataStorage
from loom.storage.resume import JDRecord, ResumeArtifact, Task
from loom.storage.usage import TokenUsage


def _profile_from_model(model: ProfileModel) -> Profile:
    """Convert ProfileModel to Profile Pydantic schema."""
    return Profile(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        name_en=model.name_en,
        name_zh=model.name_zh,
        email=model.email,
        phone=model.phone,
        phone_en=model.phone_en,
        phone_zh=model.phone_zh,
        github=model.github,
        linkedin=model.linkedin,
        certifications=model.certifications or [],
        location_en=model.location_en,
        location_zh=model.location_zh,
        summary_en=model.summary_en,
        summary_zh=model.summary_zh,
    )


def _skill_from_model(model: SkillModel) -> Skill:
    """Convert SkillModel to Skill Pydantic schema."""
    return Skill(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        profile_id=model.profile_id,
        name=model.name,
        level=model.level,
        category=model.category,
        context_en=model.context_en,
        context_zh=model.context_zh,
    )


def _experience_from_model(model: ExperienceModel) -> Experience:
    """Convert ExperienceModel to Experience Pydantic schema."""
    return Experience(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        profile_id=model.profile_id,
        company_en=model.company_en,
        company_zh=model.company_zh,
        title_en=model.title_en,
        title_zh=model.title_zh,
        location_en=model.location_en,
        location_zh=model.location_zh,
        start_date=model.start_date,
        end_date=model.end_date,
        is_visible=model.is_visible,
    )


def _education_from_model(model: EducationModel) -> Education:
    """Convert EducationModel to Education Pydantic schema."""
    return Education(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        profile_id=model.profile_id,
        institution_en=model.institution_en,
        institution_zh=model.institution_zh,
        degree_en=model.degree_en,
        degree_zh=model.degree_zh,
        field_en=model.field_en,
        field_zh=model.field_zh,
        start_date=model.start_date,
        end_date=model.end_date,
    )


def _bullet_from_model(model: BulletModel) -> Bullet:
    """Convert BulletModel to Bullet Pydantic schema."""
    return Bullet(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        experience_id=model.experience_id,
        type=model.type,
        priority=model.priority,
        content_en=model.content_en,
        content_zh=model.content_zh,
        raw_text=model.raw_text,
        star_data=model.star_data or {},
        tech_stack=model.tech_stack or [],
        jd_keywords=model.jd_keywords or [],
        confidence=model.confidence,
        missing=model.missing or [],
        is_visible=model.is_visible,
    )


def _project_from_model(model: ProjectModel) -> Project:
    """Convert ProjectModel to Project Pydantic schema."""
    return Project(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        profile_id=model.profile_id,
        experience_id=model.experience_id,
        education_id=model.education_id,
        name_en=model.name_en,
        name_zh=model.name_zh,
        description_en=model.description_en,
        description_zh=model.description_zh,
        role_en=model.role_en,
        role_zh=model.role_zh,
        start_date=model.start_date,
        end_date=model.end_date,
        tech_stack=model.tech_stack or [],
        bullets=model.bullets or [],
        is_visible=model.is_visible,
        local_repo_path=model.local_repo_path,
        last_analyzed_at=model.last_analyzed_at,
        auto_update=model.auto_update,
    )


def _jd_record_from_model(model: JDRecordModel) -> JDRecord:
    """Convert JDRecordModel to JDRecord Pydantic schema."""
    return JDRecord(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company=model.company,
        title=model.title,
        raw_text=model.raw_text,
        required_skills=model.required_skills or [],
        preferred_skills=model.preferred_skills or [],
        key_requirements=model.key_requirements or [],
        match_score=model.match_score,
    )


def _resume_artifact_from_model(model: ResumeArtifactModel) -> ResumeArtifact:
    """Convert ResumeArtifactModel to ResumeArtifact Pydantic schema."""
    return ResumeArtifact(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        jd_record_id=model.jd_record_id,
        workflow_run_id=model.workflow_run_id,
        language=model.language,
        content_md=model.content_md,
        content_tex=model.content_tex,
        pdf_path=model.pdf_path,
        starred=model.starred,
        status=model.status or "completed",
        generation_progress=model.generation_progress,
    )


def _task_from_model(model: TaskModel) -> Task:
    """Convert TaskModel to Task Pydantic schema."""
    return Task(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        type=model.type,
        status=model.status,
        input_data=model.input_data or {},
        output_data=model.output_data or {},
        error=model.error,
    )


def _token_usage_from_model(model: TokenUsageModel) -> TokenUsage:
    """Convert TokenUsageModel to TokenUsage Pydantic schema."""
    return TokenUsage(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        model=model.model,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        input_cost_usd=model.input_cost_usd,
        output_cost_usd=model.output_cost_usd,
        total_cost_usd=model.total_cost_usd,
        workflow_run_id=model.workflow_run_id,
        step_name=model.step_name,
        caller=model.caller,
    )


# Allowed columns per ORM model for safe partial updates
_PROFILE_COLUMNS = {
    "name_en", "name_zh", "email", "phone", "phone_en", "phone_zh",
    "github", "linkedin",
    "location_en", "location_zh", "summary_en", "summary_zh",
    "certifications",
}
_EXPERIENCE_COLUMNS = {
    "company_en", "company_zh", "title_en", "title_zh",
    "location_en", "location_zh", "start_date", "end_date", "is_visible",
}
_BULLET_COLUMNS = {
    "content_en", "content_zh", "raw_text", "type", "priority",
    "star_data", "tech_stack", "jd_keywords", "confidence",
    "missing", "is_visible",
}
_SKILL_COLUMNS = {
    "name", "level", "category", "context_en", "context_zh",
}
_EDUCATION_COLUMNS = {
    "institution_en", "institution_zh", "degree_en", "degree_zh",
    "field_en", "field_zh", "start_date", "end_date",
}
_PROJECT_COLUMNS = {
    "name_en", "name_zh", "description_en", "description_zh",
    "role_en", "role_zh", "start_date", "end_date",
    "tech_stack", "bullets", "is_visible", "experience_id", "education_id",
    "local_repo_path", "last_analyzed_at", "auto_update",
}



def _owner_clause(model: Any, user_id: str | None):
    """WHERE fragment restricting a row to the user who owns it.

    `None` means no owner check, and that is the path the pipeline steps, the
    CLI and the cron jobs take — they have already established whose data they
    are working on. Request handlers always pass a real user_id, so one account
    cannot reach another's row by guessing its UUID.
    """
    return true() if user_id is None else model.user_id == user_id


class PostgresDataStorage(DataStorage):
    """PostgreSQL implementation of DataStorage interface."""

    def __init__(self, session: AsyncSession | None = None):
        self._session = session

    async def _get_session(self) -> AsyncSession:
        if self._session is not None:
            return self._session
        raise RuntimeError(
            "PostgresDataStorage requires either a session or to be used "
            "via PostgresDataStorageContext"
        )

    # Profile operations
    async def save_profile(self, profile: Profile) -> None:
        session = await self._get_session()
        model = ProfileModel(
            id=profile.id,
            user_id=profile.user_id,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            name_en=profile.name_en,
            name_zh=profile.name_zh,
            email=profile.email,
            phone=profile.phone,
            phone_en=profile.phone_en,
            phone_zh=profile.phone_zh,
            github=profile.github,
            linkedin=profile.linkedin,
            certifications=profile.certifications,
            location_en=profile.location_en,
            location_zh=profile.location_zh,
            summary_en=profile.summary_en,
            summary_zh=profile.summary_zh,
        )
        session.add(model)
        await session.flush()

    async def get_profile(self, user_id: str) -> Profile | None:
        session = await self._get_session()
        result = await session.execute(
            select(ProfileModel).where(ProfileModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        return _profile_from_model(model) if model else None

    async def update_profile(self, profile_id: UUID, data: dict[str, Any]) -> Profile | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _PROFILE_COLUMNS}
        if not safe:
            return None
        await session.execute(
            update(ProfileModel).where(ProfileModel.id == profile_id).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(ProfileModel).where(ProfileModel.id == profile_id)
        )
        model = result.scalar_one_or_none()
        return _profile_from_model(model) if model else None

    # Skills
    async def save_skill(self, skill: Skill) -> None:
        session = await self._get_session()
        model = SkillModel(
            id=skill.id,
            user_id=skill.user_id,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
            profile_id=skill.profile_id,
            name=skill.name,
            level=skill.level,
            category=skill.category,
            context_en=skill.context_en,
            context_zh=skill.context_zh,
        )
        session.add(model)
        await session.flush()

    async def get_skills(self, profile_id: UUID) -> list[Skill]:
        session = await self._get_session()
        result = await session.execute(
            select(SkillModel).where(SkillModel.profile_id == profile_id)
        )
        return [_skill_from_model(m) for m in result.scalars().all()]

    async def update_skill(self, skill_id: UUID, data: dict[str, Any], user_id: str | None = None) -> Skill | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _SKILL_COLUMNS}
        if not safe:
            return None
        await session.execute(
            update(SkillModel).where(SkillModel.id == skill_id, _owner_clause(SkillModel, user_id)).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(SkillModel).where(SkillModel.id == skill_id, _owner_clause(SkillModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _skill_from_model(model) if model else None

    async def delete_skill(self, skill_id: UUID, user_id: str | None = None) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(SkillModel).where(SkillModel.id == skill_id, _owner_clause(SkillModel, user_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    # Experiences
    async def save_experience(self, exp: Experience) -> None:
        session = await self._get_session()
        model = ExperienceModel(
            id=exp.id,
            user_id=exp.user_id,
            created_at=exp.created_at,
            updated_at=exp.updated_at,
            profile_id=exp.profile_id,
            company_en=exp.company_en,
            company_zh=exp.company_zh,
            title_en=exp.title_en,
            title_zh=exp.title_zh,
            location_en=exp.location_en,
            location_zh=exp.location_zh,
            start_date=exp.start_date,
            end_date=exp.end_date,
            is_visible=exp.is_visible,
        )
        session.add(model)
        await session.flush()

    async def get_experiences(self, profile_id: UUID) -> list[Experience]:
        session = await self._get_session()
        result = await session.execute(
            select(ExperienceModel)
            .where(ExperienceModel.profile_id == profile_id)
            .order_by(
                ExperienceModel.end_date.is_(None).desc(),
                ExperienceModel.start_date.desc(),
            )
        )
        return [_experience_from_model(m) for m in result.scalars().all()]

    async def get_experience_by_id(self, exp_id: UUID, user_id: str | None = None) -> Experience | None:
        session = await self._get_session()
        result = await session.execute(
            select(ExperienceModel).where(ExperienceModel.id == exp_id, _owner_clause(ExperienceModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _experience_from_model(model) if model else None

    async def update_experience(self, exp_id: UUID, data: dict[str, Any], user_id: str | None = None) -> Experience | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _EXPERIENCE_COLUMNS}
        if not safe:
            return None
        for date_key in ("start_date", "end_date"):
            if date_key in safe and isinstance(safe[date_key], str):
                safe[date_key] = _parse_date_str(safe[date_key])
        await session.execute(
            update(ExperienceModel).where(ExperienceModel.id == exp_id, _owner_clause(ExperienceModel, user_id)).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(ExperienceModel).where(ExperienceModel.id == exp_id, _owner_clause(ExperienceModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _experience_from_model(model) if model else None

    async def delete_experience(self, exp_id: UUID, user_id: str | None = None) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(ExperienceModel).where(ExperienceModel.id == exp_id, _owner_clause(ExperienceModel, user_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    # Bullets
    async def save_bullet(self, bullet: Bullet) -> None:
        session = await self._get_session()
        model = BulletModel(
            id=bullet.id,
            user_id=bullet.user_id,
            created_at=bullet.created_at,
            updated_at=bullet.updated_at,
            experience_id=bullet.experience_id,
            type=bullet.type,
            priority=bullet.priority,
            content_en=bullet.content_en,
            content_zh=bullet.content_zh,
            raw_text=bullet.raw_text,
            star_data=bullet.star_data,
            tech_stack=bullet.tech_stack,
            jd_keywords=bullet.jd_keywords,
            confidence=bullet.confidence,
            missing=bullet.missing,
            is_visible=bullet.is_visible,
        )
        session.add(model)
        await session.flush()

    async def get_bullets(self, experience_id: UUID) -> list[Bullet]:
        session = await self._get_session()
        result = await session.execute(
            select(BulletModel).where(BulletModel.experience_id == experience_id)
        )
        return [_bullet_from_model(m) for m in result.scalars().all()]

    async def update_bullet(self, bullet_id: UUID, data: dict[str, Any], user_id: str | None = None) -> Bullet | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _BULLET_COLUMNS}
        if not safe:
            return None
        await session.execute(
            update(BulletModel).where(BulletModel.id == bullet_id, _owner_clause(BulletModel, user_id)).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(BulletModel).where(BulletModel.id == bullet_id, _owner_clause(BulletModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _bullet_from_model(model) if model else None

    async def delete_bullet(self, bullet_id: UUID, user_id: str | None = None) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(BulletModel).where(BulletModel.id == bullet_id, _owner_clause(BulletModel, user_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    # Projects
    async def save_project(self, project: Project) -> None:
        session = await self._get_session()
        model = ProjectModel(
            id=project.id,
            user_id=project.user_id,
            created_at=project.created_at,
            updated_at=project.updated_at,
            profile_id=project.profile_id,
            experience_id=project.experience_id,
            education_id=project.education_id,
            name_en=project.name_en,
            name_zh=project.name_zh,
            description_en=project.description_en,
            description_zh=project.description_zh,
            role_en=project.role_en,
            role_zh=project.role_zh,
            start_date=project.start_date,
            end_date=project.end_date,
            tech_stack=project.tech_stack,
            bullets=project.bullets,
            is_visible=project.is_visible,
            local_repo_path=project.local_repo_path,
            last_analyzed_at=project.last_analyzed_at,
            auto_update=project.auto_update,
        )
        session.add(model)
        await session.flush()

    async def get_projects(self, profile_id: UUID) -> list[Project]:
        session = await self._get_session()
        result = await session.execute(
            select(ProjectModel).where(ProjectModel.profile_id == profile_id)
        )
        return [_project_from_model(m) for m in result.scalars().all()]

    async def delete_project(self, project_id: UUID, user_id: str | None = None) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(ProjectModel).where(ProjectModel.id == project_id, _owner_clause(ProjectModel, user_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    async def update_project(self, project_id: UUID, data: dict[str, Any], user_id: str | None = None) -> Project | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _PROJECT_COLUMNS}
        if not safe:
            return None
        # Parse date strings to date objects
        for date_key in ("start_date", "end_date"):
            if date_key in safe and isinstance(safe[date_key], str):
                safe[date_key] = _parse_date_str(safe[date_key])
        await session.execute(
            update(ProjectModel).where(ProjectModel.id == project_id, _owner_clause(ProjectModel, user_id)).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(ProjectModel).where(ProjectModel.id == project_id, _owner_clause(ProjectModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _project_from_model(model) if model else None

    # Education
    async def save_education(self, edu: Education) -> None:
        session = await self._get_session()
        model = EducationModel(
            id=edu.id,
            user_id=edu.user_id,
            created_at=edu.created_at,
            updated_at=edu.updated_at,
            profile_id=edu.profile_id,
            institution_en=edu.institution_en,
            institution_zh=edu.institution_zh,
            degree_en=edu.degree_en,
            degree_zh=edu.degree_zh,
            field_en=edu.field_en,
            field_zh=edu.field_zh,
            start_date=edu.start_date,
            end_date=edu.end_date,
        )
        session.add(model)
        await session.flush()

    async def get_education(self, profile_id: UUID) -> list[Education]:
        session = await self._get_session()
        result = await session.execute(
            select(EducationModel).where(EducationModel.profile_id == profile_id)
        )
        return [_education_from_model(m) for m in result.scalars().all()]

    async def update_education(self, edu_id: UUID, data: dict[str, Any], user_id: str | None = None) -> Education | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _EDUCATION_COLUMNS}
        if not safe:
            return None
        for date_key in ("start_date", "end_date"):
            if date_key in safe and isinstance(safe[date_key], str):
                safe[date_key] = _parse_date_str(safe[date_key])
        await session.execute(
            update(EducationModel).where(EducationModel.id == edu_id, _owner_clause(EducationModel, user_id)).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(EducationModel).where(EducationModel.id == edu_id, _owner_clause(EducationModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _education_from_model(model) if model else None

    async def delete_education(self, edu_id: UUID, user_id: str | None = None) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(EducationModel).where(EducationModel.id == edu_id, _owner_clause(EducationModel, user_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    # JD Records
    async def save_jd_record(self, jd: JDRecord) -> None:
        session = await self._get_session()
        model = JDRecordModel(
            id=jd.id,
            user_id=jd.user_id,
            created_at=jd.created_at,
            updated_at=jd.updated_at,
            company=jd.company,
            title=jd.title,
            raw_text=jd.raw_text,
            required_skills=jd.required_skills,
            preferred_skills=jd.preferred_skills,
            key_requirements=jd.key_requirements,
            match_score=jd.match_score,
        )
        session.add(model)
        await session.flush()

    async def get_jd_record(self, jd_id: UUID, user_id: str | None = None) -> JDRecord | None:
        session = await self._get_session()
        result = await session.execute(
            select(JDRecordModel).where(JDRecordModel.id == jd_id, _owner_clause(JDRecordModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _jd_record_from_model(model) if model else None

    async def list_jd_records(self, user_id: str) -> list[JDRecord]:
        session = await self._get_session()
        result = await session.execute(
            select(JDRecordModel)
            .where(JDRecordModel.user_id == user_id)
            .order_by(JDRecordModel.created_at.desc())
        )
        return [_jd_record_from_model(m) for m in result.scalars().all()]

    async def update_jd_record(self, jd_id: UUID, data: dict[str, Any], user_id: str | None = None) -> JDRecord | None:
        _JD_COLUMNS = {
            "company", "title", "raw_text", "required_skills",
            "preferred_skills", "key_requirements", "match_score",
        }
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _JD_COLUMNS}
        if not safe:
            return None
        await session.execute(
            update(JDRecordModel).where(JDRecordModel.id == jd_id, _owner_clause(JDRecordModel, user_id)).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(JDRecordModel).where(JDRecordModel.id == jd_id, _owner_clause(JDRecordModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _jd_record_from_model(model) if model else None

    async def delete_jd_record(self, jd_id: UUID, user_id: str | None = None) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(JDRecordModel).where(JDRecordModel.id == jd_id, _owner_clause(JDRecordModel, user_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    async def update_jd_match_score(self, jd_id: UUID, score: float, user_id: str | None = None) -> None:
        session = await self._get_session()
        result = await session.execute(
            select(JDRecordModel).where(JDRecordModel.id == jd_id, _owner_clause(JDRecordModel, user_id))
        )
        model = result.scalar_one_or_none()
        if model:
            model.match_score = score
            await session.flush()

    # Resume Artifacts
    async def save_resume_artifact(self, artifact: ResumeArtifact) -> None:
        session = await self._get_session()
        model = ResumeArtifactModel(
            id=artifact.id,
            user_id=artifact.user_id,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
            jd_record_id=artifact.jd_record_id,
            workflow_run_id=artifact.workflow_run_id,
            language=artifact.language,
            content_md=artifact.content_md,
            content_tex=artifact.content_tex,
            pdf_path=artifact.pdf_path,
            starred=artifact.starred,
            status=artifact.status or "completed",
            generation_progress=artifact.generation_progress,
        )
        session.add(model)
        await session.flush()

    async def get_resume_artifact(self, artifact_id: UUID, user_id: str | None = None) -> ResumeArtifact | None:
        session = await self._get_session()
        result = await session.execute(
            select(ResumeArtifactModel).where(ResumeArtifactModel.id == artifact_id, _owner_clause(ResumeArtifactModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _resume_artifact_from_model(model) if model else None

    async def list_resume_artifacts(self, user_id: str) -> list[ResumeArtifact]:
        session = await self._get_session()
        result = await session.execute(
            select(ResumeArtifactModel)
            .where(ResumeArtifactModel.user_id == user_id)
            .order_by(ResumeArtifactModel.created_at.desc())
        )
        return [_resume_artifact_from_model(m) for m in result.scalars().all()]

    async def delete_resume_artifact(self, artifact_id: UUID, user_id: str | None = None) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(ResumeArtifactModel).where(ResumeArtifactModel.id == artifact_id, _owner_clause(ResumeArtifactModel, user_id))
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    async def delete_resume_artifacts_by_jd(self, jd_record_id: UUID, user_id: str | None = None) -> int:
        session = await self._get_session()
        result = await session.execute(
            select(ResumeArtifactModel)
            .where(ResumeArtifactModel.jd_record_id == jd_record_id, _owner_clause(ResumeArtifactModel, user_id))
        )
        models = result.scalars().all()
        for m in models:
            await session.delete(m)
        await session.flush()
        return len(models)

    # Resume Artifact update
    async def update_resume_artifact(self, artifact_id: UUID, data: dict[str, Any], user_id: str | None = None) -> bool:
        session = await self._get_session()
        safe_cols = {"pdf_path", "content_md", "content_tex", "language", "starred", "status", "generation_progress"}
        safe = {k: v for k, v in data.items() if k in safe_cols}
        if not safe:
            return False
        await session.execute(
            update(ResumeArtifactModel)
            .where(ResumeArtifactModel.id == artifact_id, _owner_clause(ResumeArtifactModel, user_id))
            .values(**safe)
        )
        await session.flush()
        return True

    # Tasks
    async def save_task(self, task: Task) -> None:
        session = await self._get_session()
        model = TaskModel(
            id=task.id,
            user_id=task.user_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            type=task.type,
            status=task.status,
            input_data=task.input_data,
            output_data=task.output_data,
            error=task.error,
        )
        session.add(model)
        await session.flush()

    async def get_task(self, task_id: UUID, user_id: str | None = None) -> Task | None:
        session = await self._get_session()
        result = await session.execute(
            select(TaskModel).where(TaskModel.id == task_id, _owner_clause(TaskModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _task_from_model(model) if model else None

    async def update_task(self, task_id: UUID, data: dict[str, Any], user_id: str | None = None) -> Task | None:
        session = await self._get_session()
        safe_cols = {"status", "output_data", "error"}
        safe = {k: v for k, v in data.items() if k in safe_cols}
        if not safe:
            return None
        safe["updated_at"] = datetime.utcnow()
        await session.execute(
            update(TaskModel).where(TaskModel.id == task_id, _owner_clause(TaskModel, user_id)).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(TaskModel).where(TaskModel.id == task_id, _owner_clause(TaskModel, user_id))
        )
        model = result.scalar_one_or_none()
        return _task_from_model(model) if model else None

    # Token Usage
    async def save_token_usage(self, usage: TokenUsage) -> None:
        session = await self._get_session()
        model = TokenUsageModel(
            id=usage.id,
            user_id=usage.user_id,
            created_at=usage.created_at,
            updated_at=usage.updated_at,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            input_cost_usd=usage.input_cost_usd,
            output_cost_usd=usage.output_cost_usd,
            total_cost_usd=usage.total_cost_usd,
            workflow_run_id=usage.workflow_run_id,
            step_name=usage.step_name,
            caller=usage.caller,
        )
        session.add(model)
        await session.flush()

    async def get_token_usage_by_workflow(self, workflow_run_id: UUID) -> list[TokenUsage]:
        session = await self._get_session()
        result = await session.execute(
            select(TokenUsageModel)
            .where(TokenUsageModel.workflow_run_id == workflow_run_id)
            .order_by(TokenUsageModel.created_at.desc())
        )
        return [_token_usage_from_model(m) for m in result.scalars().all()]

    async def get_token_usage_in_range(
        self, user_id: str, start: datetime, end: datetime
    ) -> list[TokenUsage]:
        session = await self._get_session()
        result = await session.execute(
            select(TokenUsageModel)
            .where(
                TokenUsageModel.user_id == user_id,
                TokenUsageModel.created_at >= start,
                TokenUsageModel.created_at <= end,
            )
            .order_by(TokenUsageModel.created_at.desc())
        )
        return [_token_usage_from_model(m) for m in result.scalars().all()]

    async def get_recent_token_usage(self, user_id: str, limit: int) -> list[TokenUsage]:
        session = await self._get_session()
        result = await session.execute(
            select(TokenUsageModel)
            .where(TokenUsageModel.user_id == user_id)
            .order_by(TokenUsageModel.created_at.desc())
            .limit(limit)
        )
        return [_token_usage_from_model(m) for m in result.scalars().all()]

    # Log Entries
    # ── Scout leads ──────────────────────────────────────────────────

    async def upsert_scout_leads(
        self, candidates: list[dict], user_id: str | None = None
    ) -> dict[str, int]:
        """Save leads, one row per place_id.

        Re-scouting an area refreshes the audit and contact details but never
        clobbers `status` or `notes` — those are the user's work, not the
        crawler's. Google-derived fields are stamped with an expiry.
        """
        from datetime import timedelta

        from loom.storage.models import GOOGLE_CACHE_DAYS, ScoutLeadModel

        user_id = user_id or get_current_user()
        session = await self._get_session()
        now = datetime.utcnow()
        expires = now + timedelta(days=GOOGLE_CACHE_DAYS)
        created = updated = 0

        for c in candidates:
            place_id = c.get("place_id")
            if not place_id:
                continue
            # Scoped to the user: two accounts scouting the same suburb each
            # keep their own row, with their own status and notes, rather than
            # the second one inheriting the first one's outreach history.
            result = await session.execute(
                select(ScoutLeadModel).where(
                    ScoutLeadModel.place_id == place_id,
                    ScoutLeadModel.user_id == user_id,
                )
            )
            row = result.scalar_one_or_none()
            audit = c.get("audit") or None
            fields = {
                "site_url": c.get("site_url"),
                "site_title": c.get("site_title"),
                "careers_url": c.get("careers_url"),
                "emails": c.get("emails") or [],
                "email_sources": c.get("email_sources") or {},
                "audit": audit,
                "score": (audit or {}).get("score", 0),
                "google_name": c.get("google_name"),
                "google_address": c.get("google_address"),
                "google_phone": c.get("google_phone"),
                "google_extra": {
                    k: c[k] for k in (
                        "google_rating", "google_rating_count", "google_price_level",
                        "google_hours", "google_maps_uri", "google_types",
                        "primary_type",
                    ) if c.get(k) not in (None, [], "")
                } or None,
                "google_expires_at": expires,
                "checked_at": now,
            }
            if row is None:
                session.add(
                    ScoutLeadModel(
                        place_id=place_id, user_id=user_id, created_at=now,
                        updated_at=now, **fields,
                    )
                )
                created += 1
            else:
                for key, value in fields.items():
                    setattr(row, key, value)
                updated += 1

        await session.flush()
        return {"created": created, "updated": updated}

    async def list_scout_leads(
        self, status: str | None = None, user_id: str | None = None, limit: int = 200
    ) -> list[dict]:
        from loom.storage.models import ScoutLeadModel

        user_id = user_id or get_current_user()
        session = await self._get_session()
        query = select(ScoutLeadModel).where(ScoutLeadModel.user_id == user_id)
        if status and status != "all":
            query = query.where(ScoutLeadModel.status == status)
        query = query.order_by(
            ScoutLeadModel.score.desc(), ScoutLeadModel.created_at.desc()
        ).limit(limit)
        result = await session.execute(query)
        rows = list(result.scalars().all())

        now = datetime.utcnow()
        expired = [r for r in rows if r.google_expires_at and r.google_expires_at < now]
        for row in expired:
            # Past the caching window — drop Google's copy rather than serve it.
            row.google_name = row.google_address = row.google_phone = None
            row.google_extra = None
            row.google_expires_at = None
        if expired:
            await session.flush()

        return [
            {
                "id": str(r.id),
                "place_id": r.place_id,
                "status": r.status,
                "notes": r.notes,
                "site_url": r.site_url,
                "site_title": r.site_title,
                "careers_url": r.careers_url,
                "emails": r.emails or [],
                "audit": r.audit,
                "score": r.score,
                "google_name": r.google_name,
                "google_address": r.google_address,
                "google_phone": r.google_phone,
                "google_extra": r.google_extra,
                "harvest": r.harvest,
                "harvested_at": r.harvested_at.isoformat() if r.harvested_at else None,
                "demo_slug": r.demo_slug,
                "demo_url": r.demo_url,
                "has_demo": bool(r.demo_html),
                "demo_active": r.demo_active,
                "demo_public": r.demo_public,
                "demo_plan": r.demo_plan,
                "planned_at": r.planned_at.isoformat() if r.planned_at else None,
                "demo_options": [
                    {
                        "direction": name,
                        "rounds": v.get("rounds"),
                        "engine": v.get("engine", "model"),
                        "remaining": v.get("remaining") or [],
                        "has_thumb": bool(v.get("thumb")),
                    }
                    for name, v in (r.demo_variants or {}).items()
                ],
                "demo_built_at": r.demo_built_at.isoformat() if r.demo_built_at else None,
                "draft_subject": r.draft_subject,
                "draft_body": r.draft_body,
                "contacted_at": r.contacted_at.isoformat() if r.contacted_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "checked_at": r.checked_at.isoformat() if r.checked_at else None,
            }
            for r in rows
        ]

    async def get_demo_by_slug(self, slug: str) -> str | None:
        """The demo page for a slug, or None. Used by the public route."""
        from loom.storage.models import ScoutLeadModel

        session = await self._get_session()
        result = await session.execute(
            select(ScoutLeadModel.demo_html).where(ScoutLeadModel.demo_slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_scout_lead(self, lead_id: str, user_id: str | None = None) -> dict | None:
        """One lead, including the heavy demo payloads.

        Not a filter over list_scout_leads: that projection deliberately drops
        demo_variants (three pages plus three screenshots) so the list stays
        small, and a single-lead fetch is exactly where those are needed.
        """
        from loom.storage.models import ScoutLeadModel

        session = await self._get_session()
        result = await session.execute(
            select(ScoutLeadModel).where(
                ScoutLeadModel.id == lead_id, _owner_clause(ScoutLeadModel, user_id)
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": str(row.id),
            "place_id": row.place_id,
            "status": row.status,
            "notes": row.notes,
            "site_url": row.site_url,
            "site_title": row.site_title,
            "careers_url": row.careers_url,
            "emails": row.emails or [],
            "email_sources": row.email_sources or {},
            "audit": row.audit,
            "score": row.score,
            "google_name": row.google_name,
            "google_address": row.google_address,
            "google_phone": row.google_phone,
            "google_extra": row.google_extra,
            "harvest": row.harvest,
            "demo_slug": row.demo_slug,
            "demo_url": row.demo_url,
            "demo_html": row.demo_html,
            "demo_variants": row.demo_variants,
            "demo_plan": row.demo_plan,
            "demo_active": row.demo_active,
            "demo_public": row.demo_public,
            "draft_subject": row.draft_subject,
            "draft_body": row.draft_body,
        }

    # Fields a pipeline stage is allowed to write back.
    _LEAD_WRITABLE = (
        "status", "notes", "emails", "harvest", "harvested_at", "demo_slug", "demo_url", "demo_html", "demo_variants", "demo_active",
        "demo_plan", "planned_at", "demo_public",
        "demo_built_at", "draft_subject", "draft_body", "drafted_at", "contacted_at",
        "email_sources",
    )

    async def update_scout_lead(
        self, lead_id: str, data: dict, user_id: str | None = None
    ) -> bool:
        from loom.storage.models import ScoutLeadModel

        session = await self._get_session()
        result = await session.execute(
            select(ScoutLeadModel).where(
                ScoutLeadModel.id == lead_id, _owner_clause(ScoutLeadModel, user_id)
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        for key in self._LEAD_WRITABLE:
            if key in data:
                setattr(row, key, data[key])
        await session.flush()
        return True

    async def delete_scout_lead(
        self, lead_id: str, user_id: str | None = None
    ) -> bool:
        from loom.storage.models import ScoutLeadModel

        session = await self._get_session()
        result = await session.execute(
            select(ScoutLeadModel).where(
                ScoutLeadModel.id == lead_id, _owner_clause(ScoutLeadModel, user_id)
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await session.delete(row)
        await session.flush()
        return True

    async def save_log_entry(self, entry: Any) -> None:
        session = await self._get_session()
        model = LogEntryModel(
            id=entry.id,
            user_id=getattr(entry, "user_id", "local"),
            created_at=entry.created_at,
            level=entry.level,
            service=getattr(entry, "service", "resume_tailor"),
            category=entry.category,
            action=entry.action,
            message=entry.message,
            workflow_run_id=entry.workflow_run_id,
            step_name=entry.step_name,
            data=entry.data,
            error=entry.error,
            traceback=entry.traceback,
        )
        session.add(model)
        await session.flush()

    async def query_logs(
        self,
        category: str | None = None,
        level: str | None = None,
        search: str | None = None,
        service: str | None = None,
        limit: int = 100,
        offset: int = 0,
        user_id: str | None = None,
    ) -> tuple[list[dict], int]:
        session = await self._get_session()
        owner = _owner_clause(LogEntryModel, user_id)
        query = select(LogEntryModel).where(owner)
        count_query = select(func.count(LogEntryModel.id)).where(owner)
        if service:
            query = query.where(LogEntryModel.service == service)
            count_query = count_query.where(LogEntryModel.service == service)
        if category:
            query = query.where(LogEntryModel.category == category)
            count_query = count_query.where(LogEntryModel.category == category)
        if level:
            query = query.where(LogEntryModel.level == level)
            count_query = count_query.where(LogEntryModel.level == level)
        if search:
            pattern = f"%{search}%"
            search_filter = LogEntryModel.message.ilike(pattern) | LogEntryModel.action.ilike(pattern)
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(LogEntryModel.created_at.desc()).offset(offset).limit(limit)
        result = await session.execute(query)
        entries = [
            {
                "id": str(m.id),
                "level": m.level,
                "service": getattr(m, "service", "resume_tailor"),
                "category": m.category,
                "action": m.action,
                "message": m.message,
                "workflow_run_id": str(m.workflow_run_id) if m.workflow_run_id else None,
                "step_name": m.step_name,
                "data": m.data or {},
                "error": m.error,
                "traceback": m.traceback,
                "created_at": m.created_at.isoformat(),
            }
            for m in result.scalars().all()
        ]
        return entries, total

    async def delete_logs(self, older_than_days: int = 0, user_id: str | None = None) -> int:
        session = await self._get_session()
        owner = _owner_clause(LogEntryModel, user_id)
        if older_than_days == 0:
            result = await session.execute(delete(LogEntryModel).where(owner))
        else:
            cutoff = datetime.utcnow() - __import__("datetime").timedelta(days=older_than_days)
            result = await session.execute(
                delete(LogEntryModel).where(LogEntryModel.created_at < cutoff, owner)
            )
        await session.flush()
        return result.rowcount or 0

    async def get_log_stats(self, user_id: str | None = None) -> dict[str, Any]:
        session = await self._get_session()
        owner = _owner_clause(LogEntryModel, user_id)
        spender = _owner_clause(TokenUsageModel, user_id)
        total_r = await session.execute(
            select(func.count(LogEntryModel.id)).where(owner)
        )
        total = total_r.scalar() or 0

        cat_r = await session.execute(
            select(LogEntryModel.category, func.count(LogEntryModel.id))
            .where(owner)
            .group_by(LogEntryModel.category)
        )
        by_category = {row[0]: row[1] for row in cat_r.all()}

        level_r = await session.execute(
            select(LogEntryModel.level, func.count(LogEntryModel.id))
            .where(owner)
            .group_by(LogEntryModel.level)
        )
        by_level = {row[0]: row[1] for row in level_r.all()}

        oldest_r = await session.execute(
            select(func.min(LogEntryModel.created_at)).where(owner)
        )
        newest_r = await session.execute(
            select(func.max(LogEntryModel.created_at)).where(owner)
        )
        oldest = oldest_r.scalar()
        newest = newest_r.scalar()

        # Was hardcoded to 0 — never a regression, just never implemented, so
        # the dashboard has always reported no spend at all.
        usage_r = await session.execute(
            select(
                func.coalesce(func.sum(TokenUsageModel.input_tokens), 0),
                func.coalesce(func.sum(TokenUsageModel.output_tokens), 0),
                func.count(TokenUsageModel.id),
            ).where(spender)
        )
        input_tokens, output_tokens, calls = usage_r.first() or (0, 0, 0)

        by_caller_r = await session.execute(
            select(
                TokenUsageModel.step_name,
                func.count(TokenUsageModel.id),
                func.sum(TokenUsageModel.input_tokens + TokenUsageModel.output_tokens),
            ).where(spender).group_by(TokenUsageModel.step_name)
        )
        by_caller = {
            (row[0] or "unattributed"): {"calls": row[1], "tokens": row[2] or 0}
            for row in by_caller_r.all()
        }

        return {
            "total_entries": total,
            "by_category": by_category,
            "by_level": by_level,
            "total_tokens_used": int(input_tokens) + int(output_tokens),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "llm_calls": int(calls),
            "tokens_by_caller": by_caller,
            "oldest_entry": oldest.isoformat() if oldest else None,
            "newest_entry": newest.isoformat() if newest else None,
        }


class PostgresDataStorageContext:
    """Context manager wrapper for PostgresDataStorage."""

    def __init__(self):
        self._session = None
        self._storage = None
        self._context = None

    async def __aenter__(self) -> PostgresDataStorage:
        self._context = get_session()
        self._session = await self._context.__aenter__()
        self._storage = PostgresDataStorage(session=self._session)
        return self._storage

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._context:
            await self._context.__aexit__(exc_type, exc_val, exc_tb)


class AutocommitPostgresStorage(DataStorage):
    """PostgreSQL storage that auto-creates a session per operation.

    Each method call opens a session, runs the operation, commits, and closes.
    Safe for use as a long-lived singleton in FastAPI without manual session management.
    """

    async def _run(self, method_name: str, *args, **kwargs):
        async with PostgresDataStorageContext() as pg:
            method = getattr(pg, method_name)
            return await method(*args, **kwargs)

    # Profile
    async def save_profile(self, profile, **kwargs):
        return await self._run("save_profile", profile, **kwargs)

    async def get_profile(self, user_id, **kwargs):
        return await self._run("get_profile", user_id, **kwargs)

    async def update_profile(self, profile_id, data, **kwargs):
        return await self._run("update_profile", profile_id, data, **kwargs)

    # Skills
    async def save_skill(self, skill, **kwargs):
        return await self._run("save_skill", skill, **kwargs)

    async def get_skills(self, profile_id, **kwargs):
        return await self._run("get_skills", profile_id, **kwargs)

    async def update_skill(self, skill_id, data, **kwargs):
        return await self._run("update_skill", skill_id, data, **kwargs)

    async def delete_skill(self, skill_id, **kwargs):
        return await self._run("delete_skill", skill_id, **kwargs)

    # Experiences
    async def save_experience(self, exp, **kwargs):
        return await self._run("save_experience", exp, **kwargs)

    async def get_experiences(self, profile_id, **kwargs):
        return await self._run("get_experiences", profile_id, **kwargs)

    async def get_experience_by_id(self, exp_id, **kwargs):
        return await self._run("get_experience_by_id", exp_id, **kwargs)

    async def update_experience(self, exp_id, data, **kwargs):
        return await self._run("update_experience", exp_id, data, **kwargs)

    async def delete_experience(self, exp_id, **kwargs):
        return await self._run("delete_experience", exp_id, **kwargs)

    # Bullets
    async def save_bullet(self, bullet, **kwargs):
        return await self._run("save_bullet", bullet, **kwargs)

    async def get_bullets(self, experience_id, **kwargs):
        return await self._run("get_bullets", experience_id, **kwargs)

    async def update_bullet(self, bullet_id, data, **kwargs):
        return await self._run("update_bullet", bullet_id, data, **kwargs)

    async def delete_bullet(self, bullet_id, **kwargs):
        return await self._run("delete_bullet", bullet_id, **kwargs)

    # Projects
    async def save_project(self, project, **kwargs):
        return await self._run("save_project", project, **kwargs)

    async def get_projects(self, profile_id, **kwargs):
        return await self._run("get_projects", profile_id, **kwargs)

    async def update_project(self, project_id, data, **kwargs):
        return await self._run("update_project", project_id, data, **kwargs)

    async def delete_project(self, project_id, **kwargs):
        return await self._run("delete_project", project_id, **kwargs)

    # Education
    async def save_education(self, edu, **kwargs):
        return await self._run("save_education", edu, **kwargs)

    async def get_education(self, profile_id, **kwargs):
        return await self._run("get_education", profile_id, **kwargs)

    async def update_education(self, edu_id, data, **kwargs):
        return await self._run("update_education", edu_id, data, **kwargs)

    async def delete_education(self, edu_id, **kwargs):
        return await self._run("delete_education", edu_id, **kwargs)

    # JD Records
    async def save_jd_record(self, jd, **kwargs):
        return await self._run("save_jd_record", jd, **kwargs)

    async def get_jd_record(self, jd_id, **kwargs):
        return await self._run("get_jd_record", jd_id, **kwargs)

    async def list_jd_records(self, user_id, **kwargs):
        return await self._run("list_jd_records", user_id, **kwargs)

    async def delete_jd_record(self, jd_id, **kwargs):
        return await self._run("delete_jd_record", jd_id, **kwargs)

    async def update_jd_record(self, jd_id, data, **kwargs):
        return await self._run("update_jd_record", jd_id, data, **kwargs)

    async def update_jd_match_score(self, jd_id, score, **kwargs):
        return await self._run("update_jd_match_score", jd_id, score, **kwargs)

    # Resume Artifacts
    async def save_resume_artifact(self, artifact, **kwargs):
        return await self._run("save_resume_artifact", artifact, **kwargs)

    async def get_resume_artifact(self, artifact_id, **kwargs):
        return await self._run("get_resume_artifact", artifact_id, **kwargs)

    async def list_resume_artifacts(self, user_id, **kwargs):
        return await self._run("list_resume_artifacts", user_id, **kwargs)

    async def delete_resume_artifact(self, artifact_id, **kwargs):
        return await self._run("delete_resume_artifact", artifact_id, **kwargs)

    async def delete_resume_artifacts_by_jd(self, jd_record_id, **kwargs):
        return await self._run("delete_resume_artifacts_by_jd", jd_record_id, **kwargs)

    async def update_resume_artifact(self, artifact_id, data, **kwargs):
        return await self._run("update_resume_artifact", artifact_id, data, **kwargs)

    # Tasks
    async def save_task(self, task, **kwargs):
        return await self._run("save_task", task, **kwargs)

    async def get_task(self, task_id, **kwargs):
        return await self._run("get_task", task_id, **kwargs)

    async def update_task(self, task_id, data, **kwargs):
        return await self._run("update_task", task_id, data, **kwargs)

    # Token Usage
    async def save_token_usage(self, usage, **kwargs):
        return await self._run("save_token_usage", usage, **kwargs)

    async def get_token_usage_by_workflow(self, workflow_run_id, **kwargs):
        return await self._run("get_token_usage_by_workflow", workflow_run_id, **kwargs)

    async def get_token_usage_in_range(self, user_id, start, end, **kwargs):
        return await self._run("get_token_usage_in_range", user_id, start, end, **kwargs)

    async def get_recent_token_usage(self, user_id, limit, **kwargs):
        return await self._run("get_recent_token_usage", user_id, limit, **kwargs)

    # Logs
    async def upsert_scout_leads(self, candidates, user_id=None, **kwargs):
        return await self._run("upsert_scout_leads", candidates, user_id=user_id, **kwargs)

    async def list_scout_leads(self, status=None, user_id=None, limit=200, **kwargs):
        return await self._run("list_scout_leads", status=status, user_id=user_id, limit=limit, **kwargs)

    async def get_demo_by_slug(self, slug, **kwargs):
        return await self._run("get_demo_by_slug", slug, **kwargs)

    async def get_scout_lead(self, lead_id, **kwargs):
        return await self._run("get_scout_lead", lead_id, **kwargs)

    async def update_scout_lead(self, lead_id, data, **kwargs):
        return await self._run("update_scout_lead", lead_id, data, **kwargs)

    async def delete_scout_lead(self, lead_id, **kwargs):
        return await self._run("delete_scout_lead", lead_id, **kwargs)

    async def save_log_entry(self, entry, **kwargs):
        return await self._run("save_log_entry", entry, **kwargs)

    async def query_logs(self, category=None, level=None, search=None, service=None, limit=100, offset=0, **kwargs):
        return await self._run("query_logs", category=category, level=level, search=search, service=service, limit=limit, offset=offset, **kwargs)

    async def delete_logs(self, older_than_days=0, **kwargs):
        return await self._run("delete_logs", older_than_days, **kwargs)

    async def get_log_stats(self, **kwargs):
        return await self._run("get_log_stats", **kwargs)
