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

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def update_skill(self, skill_id: UUID, data: dict[str, Any]) -> Skill | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _SKILL_COLUMNS}
        if not safe:
            return None
        await session.execute(
            update(SkillModel).where(SkillModel.id == skill_id).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(SkillModel).where(SkillModel.id == skill_id)
        )
        model = result.scalar_one_or_none()
        return _skill_from_model(model) if model else None

    async def delete_skill(self, skill_id: UUID) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(SkillModel).where(SkillModel.id == skill_id)
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
            select(ExperienceModel).where(ExperienceModel.profile_id == profile_id)
        )
        return [_experience_from_model(m) for m in result.scalars().all()]

    async def get_experience_by_id(self, exp_id: UUID) -> Experience | None:
        session = await self._get_session()
        result = await session.execute(
            select(ExperienceModel).where(ExperienceModel.id == exp_id)
        )
        model = result.scalar_one_or_none()
        return _experience_from_model(model) if model else None

    async def update_experience(self, exp_id: UUID, data: dict[str, Any]) -> Experience | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _EXPERIENCE_COLUMNS}
        if not safe:
            return None
        for date_key in ("start_date", "end_date"):
            if date_key in safe and isinstance(safe[date_key], str):
                safe[date_key] = _parse_date_str(safe[date_key])
        await session.execute(
            update(ExperienceModel).where(ExperienceModel.id == exp_id).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(ExperienceModel).where(ExperienceModel.id == exp_id)
        )
        model = result.scalar_one_or_none()
        return _experience_from_model(model) if model else None

    async def delete_experience(self, exp_id: UUID) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(ExperienceModel).where(ExperienceModel.id == exp_id)
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

    async def update_bullet(self, bullet_id: UUID, data: dict[str, Any]) -> Bullet | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _BULLET_COLUMNS}
        if not safe:
            return None
        await session.execute(
            update(BulletModel).where(BulletModel.id == bullet_id).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(BulletModel).where(BulletModel.id == bullet_id)
        )
        model = result.scalar_one_or_none()
        return _bullet_from_model(model) if model else None

    async def delete_bullet(self, bullet_id: UUID) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(BulletModel).where(BulletModel.id == bullet_id)
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

    async def delete_project(self, project_id: UUID) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(ProjectModel).where(ProjectModel.id == project_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    async def update_project(self, project_id: UUID, data: dict[str, Any]) -> Project | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _PROJECT_COLUMNS}
        if not safe:
            return None
        # Parse date strings to date objects
        for date_key in ("start_date", "end_date"):
            if date_key in safe and isinstance(safe[date_key], str):
                safe[date_key] = _parse_date_str(safe[date_key])
        await session.execute(
            update(ProjectModel).where(ProjectModel.id == project_id).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(ProjectModel).where(ProjectModel.id == project_id)
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

    async def update_education(self, edu_id: UUID, data: dict[str, Any]) -> Education | None:
        session = await self._get_session()
        safe = {k: v for k, v in data.items() if k in _EDUCATION_COLUMNS}
        if not safe:
            return None
        for date_key in ("start_date", "end_date"):
            if date_key in safe and isinstance(safe[date_key], str):
                safe[date_key] = _parse_date_str(safe[date_key])
        await session.execute(
            update(EducationModel).where(EducationModel.id == edu_id).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(EducationModel).where(EducationModel.id == edu_id)
        )
        model = result.scalar_one_or_none()
        return _education_from_model(model) if model else None

    async def delete_education(self, edu_id: UUID) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(EducationModel).where(EducationModel.id == edu_id)
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

    async def get_jd_record(self, jd_id: UUID) -> JDRecord | None:
        session = await self._get_session()
        result = await session.execute(
            select(JDRecordModel).where(JDRecordModel.id == jd_id)
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

    async def delete_jd_record(self, jd_id: UUID) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(JDRecordModel).where(JDRecordModel.id == jd_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    async def update_jd_match_score(self, jd_id: UUID, score: float) -> None:
        session = await self._get_session()
        result = await session.execute(
            select(JDRecordModel).where(JDRecordModel.id == jd_id)
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

    async def get_resume_artifact(self, artifact_id: UUID) -> ResumeArtifact | None:
        session = await self._get_session()
        result = await session.execute(
            select(ResumeArtifactModel).where(ResumeArtifactModel.id == artifact_id)
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

    async def delete_resume_artifact(self, artifact_id: UUID) -> bool:
        session = await self._get_session()
        result = await session.execute(
            select(ResumeArtifactModel).where(ResumeArtifactModel.id == artifact_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await session.delete(model)
        await session.flush()
        return True

    async def delete_resume_artifacts_by_jd(self, jd_record_id: UUID) -> int:
        session = await self._get_session()
        result = await session.execute(
            select(ResumeArtifactModel)
            .where(ResumeArtifactModel.jd_record_id == jd_record_id)
        )
        models = result.scalars().all()
        for m in models:
            await session.delete(m)
        await session.flush()
        return len(models)

    # Resume Artifact update
    async def update_resume_artifact(self, artifact_id: UUID, data: dict[str, Any]) -> bool:
        session = await self._get_session()
        safe_cols = {"pdf_path", "content_md", "content_tex", "language", "starred", "status", "generation_progress"}
        safe = {k: v for k, v in data.items() if k in safe_cols}
        if not safe:
            return False
        await session.execute(
            update(ResumeArtifactModel)
            .where(ResumeArtifactModel.id == artifact_id)
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

    async def get_task(self, task_id: UUID) -> Task | None:
        session = await self._get_session()
        result = await session.execute(
            select(TaskModel).where(TaskModel.id == task_id)
        )
        model = result.scalar_one_or_none()
        return _task_from_model(model) if model else None

    async def update_task(self, task_id: UUID, data: dict[str, Any]) -> Task | None:
        session = await self._get_session()
        safe_cols = {"status", "output_data", "error"}
        safe = {k: v for k, v in data.items() if k in safe_cols}
        if not safe:
            return None
        safe["updated_at"] = datetime.utcnow()
        await session.execute(
            update(TaskModel).where(TaskModel.id == task_id).values(**safe)
        )
        await session.flush()
        result = await session.execute(
            select(TaskModel).where(TaskModel.id == task_id)
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
    async def save_log_entry(self, entry: Any) -> None:
        session = await self._get_session()
        model = LogEntryModel(
            id=entry.id,
            user_id=getattr(entry, "user_id", "local"),
            created_at=entry.created_at,
            level=entry.level,
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
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        session = await self._get_session()
        query = select(LogEntryModel)
        count_query = select(func.count(LogEntryModel.id))
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

    async def delete_logs(self, older_than_days: int = 0) -> int:
        session = await self._get_session()
        if older_than_days == 0:
            result = await session.execute(delete(LogEntryModel))
        else:
            cutoff = datetime.utcnow() - __import__("datetime").timedelta(days=older_than_days)
            result = await session.execute(
                delete(LogEntryModel).where(LogEntryModel.created_at < cutoff)
            )
        await session.flush()
        return result.rowcount or 0

    async def get_log_stats(self) -> dict[str, Any]:
        session = await self._get_session()
        total_r = await session.execute(select(func.count(LogEntryModel.id)))
        total = total_r.scalar() or 0

        cat_r = await session.execute(
            select(LogEntryModel.category, func.count(LogEntryModel.id))
            .group_by(LogEntryModel.category)
        )
        by_category = {row[0]: row[1] for row in cat_r.all()}

        level_r = await session.execute(
            select(LogEntryModel.level, func.count(LogEntryModel.id))
            .group_by(LogEntryModel.level)
        )
        by_level = {row[0]: row[1] for row in level_r.all()}

        oldest_r = await session.execute(
            select(func.min(LogEntryModel.created_at))
        )
        newest_r = await session.execute(
            select(func.max(LogEntryModel.created_at))
        )
        oldest = oldest_r.scalar()
        newest = newest_r.scalar()

        return {
            "total_entries": total,
            "by_category": by_category,
            "by_level": by_level,
            "total_tokens_used": 0,
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
    async def save_profile(self, profile):
        return await self._run("save_profile", profile)

    async def get_profile(self, user_id):
        return await self._run("get_profile", user_id)

    async def update_profile(self, profile_id, data):
        return await self._run("update_profile", profile_id, data)

    # Skills
    async def save_skill(self, skill):
        return await self._run("save_skill", skill)

    async def get_skills(self, profile_id):
        return await self._run("get_skills", profile_id)

    async def update_skill(self, skill_id, data):
        return await self._run("update_skill", skill_id, data)

    async def delete_skill(self, skill_id):
        return await self._run("delete_skill", skill_id)

    # Experiences
    async def save_experience(self, exp):
        return await self._run("save_experience", exp)

    async def get_experiences(self, profile_id):
        return await self._run("get_experiences", profile_id)

    async def get_experience_by_id(self, exp_id):
        return await self._run("get_experience_by_id", exp_id)

    async def update_experience(self, exp_id, data):
        return await self._run("update_experience", exp_id, data)

    async def delete_experience(self, exp_id):
        return await self._run("delete_experience", exp_id)

    # Bullets
    async def save_bullet(self, bullet):
        return await self._run("save_bullet", bullet)

    async def get_bullets(self, experience_id):
        return await self._run("get_bullets", experience_id)

    async def update_bullet(self, bullet_id, data):
        return await self._run("update_bullet", bullet_id, data)

    async def delete_bullet(self, bullet_id):
        return await self._run("delete_bullet", bullet_id)

    # Projects
    async def save_project(self, project):
        return await self._run("save_project", project)

    async def get_projects(self, profile_id):
        return await self._run("get_projects", profile_id)

    async def update_project(self, project_id, data):
        return await self._run("update_project", project_id, data)

    async def delete_project(self, project_id):
        return await self._run("delete_project", project_id)

    # Education
    async def save_education(self, edu):
        return await self._run("save_education", edu)

    async def get_education(self, profile_id):
        return await self._run("get_education", profile_id)

    async def update_education(self, edu_id, data):
        return await self._run("update_education", edu_id, data)

    async def delete_education(self, edu_id):
        return await self._run("delete_education", edu_id)

    # JD Records
    async def save_jd_record(self, jd):
        return await self._run("save_jd_record", jd)

    async def get_jd_record(self, jd_id):
        return await self._run("get_jd_record", jd_id)

    async def list_jd_records(self, user_id):
        return await self._run("list_jd_records", user_id)

    async def delete_jd_record(self, jd_id):
        return await self._run("delete_jd_record", jd_id)

    async def update_jd_match_score(self, jd_id, score):
        return await self._run("update_jd_match_score", jd_id, score)

    # Resume Artifacts
    async def save_resume_artifact(self, artifact):
        return await self._run("save_resume_artifact", artifact)

    async def get_resume_artifact(self, artifact_id):
        return await self._run("get_resume_artifact", artifact_id)

    async def list_resume_artifacts(self, user_id):
        return await self._run("list_resume_artifacts", user_id)

    async def delete_resume_artifact(self, artifact_id):
        return await self._run("delete_resume_artifact", artifact_id)

    async def delete_resume_artifacts_by_jd(self, jd_record_id):
        return await self._run("delete_resume_artifacts_by_jd", jd_record_id)

    async def update_resume_artifact(self, artifact_id, data):
        return await self._run("update_resume_artifact", artifact_id, data)

    # Tasks
    async def save_task(self, task):
        return await self._run("save_task", task)

    async def get_task(self, task_id):
        return await self._run("get_task", task_id)

    async def update_task(self, task_id, data):
        return await self._run("update_task", task_id, data)

    # Token Usage
    async def save_token_usage(self, usage):
        return await self._run("save_token_usage", usage)

    async def get_token_usage_by_workflow(self, workflow_run_id):
        return await self._run("get_token_usage_by_workflow", workflow_run_id)

    async def get_token_usage_in_range(self, user_id, start, end):
        return await self._run("get_token_usage_in_range", user_id, start, end)

    async def get_recent_token_usage(self, user_id, limit):
        return await self._run("get_recent_token_usage", user_id, limit)

    # Logs
    async def save_log_entry(self, entry):
        return await self._run("save_log_entry", entry)

    async def query_logs(self, category=None, level=None, search=None, limit=100, offset=0):
        return await self._run("query_logs", category=category, level=level, search=search, limit=limit, offset=offset)

    async def delete_logs(self, older_than_days=0):
        return await self._run("delete_logs", older_than_days)

    async def get_log_stats(self):
        return await self._run("get_log_stats")
