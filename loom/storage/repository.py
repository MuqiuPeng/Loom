"""Repository layer for data access."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from loom.storage.base import BaseEntity
from loom.storage.bullet import Bullet
from loom.storage.profile import Education, Experience, Profile, Skill
from loom.storage.project import Project
from loom.storage.resume import JDRecord, ResumeArtifact, Task
from loom.storage.usage import TokenUsage, UsageSummary


def _bilingual(en: str | None, zh: str | None, lang: str) -> str | None:
    """Return the value for the requested language, falling back en -> zh."""
    if lang == "zh":
        return zh if zh else en
    return en


class ProfileRepository:
    """Repository for fetching profile data.

    Provides methods to get complete profile with all related data
    for matching against job descriptions.
    """

    def __init__(self, storage: "DataStorage | None" = None):
        self.storage = storage or InMemoryDataStorage()

    async def get_full_profile(
        self, user_id: str = "local", lang: str = "en",
    ) -> dict[str, Any] | None:
        """Get complete profile with skills, experiences, bullets, projects.

        Args:
            user_id: User ID to fetch profile for.
            lang: Language code ("en" or "zh"). zh falls back to en when empty.

        Returns dict with:
        - profile: Profile basic info
        - skills: List of Skill with name, level, context
        - experiences: List of Experience with bullets
        - projects: List of Project
        - education: List of Education

        Returns None if no profile exists.
        """
        profile = await self.storage.get_profile(user_id)
        if not profile:
            return None

        skills = await self.storage.get_skills(profile.id)
        experiences = await self.storage.get_experiences(profile.id)
        projects = await self.storage.get_projects(profile.id)
        education = await self.storage.get_education(profile.id)

        def _serialize_project(p: Project) -> dict:
            return {
                "id": str(p.id),
                "experience_id": str(p.experience_id) if p.experience_id else None,
                "education_id": str(p.education_id) if p.education_id else None,
                "name": _bilingual(p.name_en, p.name_zh, lang),
                "description": _bilingual(p.description_en, p.description_zh, lang),
                "role": _bilingual(p.role_en, p.role_zh, lang),
                "start_date": str(p.start_date) if p.start_date else None,
                "end_date": str(p.end_date) if p.end_date else None,
                "tech_stack": p.tech_stack,
                "bullets": [
                    {
                        **b,
                        "content": _bilingual(
                            b.get("content_en"), b.get("content_zh"), lang,
                        ),
                    }
                    for b in p.bullets
                ],
                "local_repo_path": p.local_repo_path,
                "last_analyzed_at": p.last_analyzed_at.isoformat() if p.last_analyzed_at else None,
                "has_local_repo": bool(p.local_repo_path),
                "is_visible": p.is_visible,
            }

        # Index projects by experience_id
        projects_by_exp: dict[UUID, list[dict]] = {}
        standalone_projects: list[dict] = []
        for p in projects:
            serialized = _serialize_project(p)
            if p.experience_id:
                projects_by_exp.setdefault(p.experience_id, []).append(serialized)
            else:
                standalone_projects.append(serialized)

        # Fetch bullets for each experience, attach linked projects
        experiences_with_bullets = []
        for exp in experiences:
            bullets = await self.storage.get_bullets(exp.id)
            experiences_with_bullets.append({
                "id": str(exp.id),
                "company": _bilingual(exp.company_en, exp.company_zh, lang),
                "title": _bilingual(exp.title_en, exp.title_zh, lang),
                "location": _bilingual(exp.location_en, exp.location_zh, lang),
                "start_date": str(exp.start_date) if exp.start_date else None,
                "end_date": str(exp.end_date) if exp.end_date else None,
                "is_visible": exp.is_visible,
                "bullets": [
                    {
                        "id": str(b.id),
                        "content": _bilingual(b.content_en, b.content_zh, lang),
                        "raw_text": b.raw_text,
                        "star_data": b.star_data,
                        "type": b.type.value,
                        "tech_stack": b.tech_stack,
                    }
                    for b in bullets if b.is_visible
                ],
                "projects": projects_by_exp.get(exp.id, []),
            })

        return {
            "profile": {
                "id": str(profile.id),
                "name": _bilingual(profile.name_en, profile.name_zh, lang),
                "email": profile.email,
                "phone": _bilingual(profile.phone_en, profile.phone_zh, lang) or profile.phone,
                "github": profile.github,
                "linkedin": profile.linkedin,
                "location": _bilingual(profile.location_en, profile.location_zh, lang),
                "summary": _bilingual(profile.summary_en, profile.summary_zh, lang),
                "certifications": profile.certifications or [],
            },
            "skills": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "level": s.level.value,
                    "category": s.category,
                    "context": _bilingual(s.context_en, s.context_zh, lang),
                }
                for s in skills
            ],
            "experiences": experiences_with_bullets,
            "projects": standalone_projects,
            "education": [
                {
                    "id": str(e.id),
                    "institution": _bilingual(e.institution_en, e.institution_zh, lang),
                    "degree": _bilingual(e.degree_en, e.degree_zh, lang),
                    "field": _bilingual(e.field_en, e.field_zh, lang),
                    "start_date": str(e.start_date) if e.start_date else None,
                    "end_date": str(e.end_date) if e.end_date else None,
                }
                for e in education
            ],
        }

    async def update_basic_info(
        self, profile_id: UUID, data: dict[str, Any],
    ) -> Profile | None:
        """Update profile basic info fields (supports bilingual)."""
        return await self.storage.update_profile(profile_id, data)

    async def update_experience(
        self, exp_id: UUID, data: dict[str, Any],
    ) -> Experience | None:
        """Update an experience entry (supports bilingual fields)."""
        return await self.storage.update_experience(exp_id, data)

    async def update_bullet(
        self, bullet_id: UUID, data: dict[str, Any],
    ) -> Bullet | None:
        """Update a bullet entry."""
        return await self.storage.update_bullet(bullet_id, data)

    async def delete_bullet(self, bullet_id: UUID) -> bool:
        """Delete a bullet by ID. Returns True if found and deleted."""
        return await self.storage.delete_bullet(bullet_id)

    async def add_bullet(
        self, experience_id: UUID, data: dict[str, Any],
    ) -> Bullet:
        """Create and save a new bullet under an experience."""
        bullet = Bullet(experience_id=experience_id, **data)
        await self.storage.save_bullet(bullet)
        return bullet


class JDRepository:
    """Repository for JD records."""

    def __init__(self, storage: "DataStorage | None" = None):
        self.storage = storage or InMemoryDataStorage()

    async def get_jd_record(self, jd_id: UUID) -> JDRecord | None:
        return await self.storage.get_jd_record(jd_id)

    async def update_match_score(self, jd_id: UUID, score: float) -> None:
        await self.storage.update_jd_match_score(jd_id, score)


class BulletRepository:
    """Repository for bullet operations."""

    def __init__(self, storage: "DataStorage | None" = None):
        self.storage = storage or InMemoryDataStorage()

    async def get_all_bullets_for_user(
        self, user_id: str = "local"
    ) -> list[tuple[Experience, list[Bullet]]]:
        """Get all bullets grouped by experience for a user.

        Returns list of (Experience, [Bullet]) tuples,
        sorted by Experience.start_date descending (most recent first).
        """
        profile = await self.storage.get_profile(user_id)
        if not profile:
            return []

        experiences = await self.storage.get_experiences(profile.id)

        # Sort by start_date descending (most recent first)
        experiences = sorted(
            experiences,
            key=lambda e: e.start_date or "0000-00-00",
            reverse=True,
        )

        result = []
        for exp in experiences:
            if not exp.is_visible:
                continue
            bullets = await self.storage.get_bullets(exp.id)
            result.append((exp, bullets))

        return result


class ResumeRepository:
    """Repository for resume artifacts."""

    def __init__(self, storage: "DataStorage | None" = None):
        self.storage = storage or InMemoryDataStorage()

    async def save_artifact(self, artifact: ResumeArtifact) -> None:
        await self.storage.save_resume_artifact(artifact)

    async def get_artifact(self, artifact_id: UUID) -> ResumeArtifact | None:
        return await self.storage.get_resume_artifact(artifact_id)


class ExperienceRepository:
    """Repository for experience data."""

    def __init__(self, storage: "DataStorage | None" = None):
        self.storage = storage or InMemoryDataStorage()

    async def get_experience_by_id(self, exp_id: UUID) -> Experience | None:
        return await self.storage.get_experience_by_id(exp_id)

    async def get_experiences_by_ids(self, exp_ids: list[UUID]) -> dict[UUID, Experience]:
        """Get multiple experiences by their IDs."""
        result = {}
        for exp_id in exp_ids:
            exp = await self.storage.get_experience_by_id(exp_id)
            if exp:
                result[exp_id] = exp
        return result


class UsageRepository:
    """Repository for token usage tracking and statistics."""

    def __init__(self, storage: "DataStorage | None" = None):
        self.storage = storage or InMemoryDataStorage()

    async def record_usage(self, usage: TokenUsage) -> None:
        """Record a single token usage entry."""
        await self.storage.save_token_usage(usage)

    async def get_usage_by_workflow(self, workflow_run_id: UUID) -> list[TokenUsage]:
        """Get all usage records for a workflow run."""
        return await self.storage.get_token_usage_by_workflow(workflow_run_id)

    async def get_usage_summary(
        self,
        user_id: str = "local",
        days: int = 30,
    ) -> UsageSummary:
        """Get aggregated usage summary for a time period."""
        end = datetime.utcnow()
        start = end - timedelta(days=days)

        usages = await self.storage.get_token_usage_in_range(user_id, start, end)

        # Aggregate statistics
        total_calls = len(usages)
        total_input = sum(u.input_tokens for u in usages)
        total_output = sum(u.output_tokens for u in usages)
        total_cost = sum(Decimal(u.total_cost_usd) for u in usages)

        # Breakdown by model
        by_model: dict[str, dict] = {}
        for u in usages:
            if u.model not in by_model:
                by_model[u.model] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": Decimal("0"),
                }
            by_model[u.model]["calls"] += 1
            by_model[u.model]["input_tokens"] += u.input_tokens
            by_model[u.model]["output_tokens"] += u.output_tokens
            by_model[u.model]["cost_usd"] += Decimal(u.total_cost_usd)

        # Convert Decimal to string for JSON serialization
        for model in by_model:
            by_model[model]["cost_usd"] = str(by_model[model]["cost_usd"])

        # Breakdown by step
        by_step: dict[str, dict] = {}
        for u in usages:
            step = u.step_name or "unknown"
            if step not in by_step:
                by_step[step] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": Decimal("0"),
                }
            by_step[step]["calls"] += 1
            by_step[step]["input_tokens"] += u.input_tokens
            by_step[step]["output_tokens"] += u.output_tokens
            by_step[step]["cost_usd"] += Decimal(u.total_cost_usd)

        for step in by_step:
            by_step[step]["cost_usd"] = str(by_step[step]["cost_usd"])

        return UsageSummary(
            user_id=user_id,
            period_start=start,
            period_end=end,
            total_calls=total_calls,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost_usd=str(total_cost),
            by_model=by_model,
            by_step=by_step,
        )

    async def get_recent_usage(
        self,
        user_id: str = "local",
        limit: int = 20,
    ) -> list[TokenUsage]:
        """Get most recent usage records."""
        return await self.storage.get_recent_token_usage(user_id, limit)


class DataStorage:
    """Abstract interface for data persistence."""

    async def get_profile(self, user_id: str) -> Profile | None:
        raise NotImplementedError

    async def update_profile(self, profile_id: UUID, data: dict[str, Any]) -> Profile | None:
        raise NotImplementedError

    async def get_skills(self, profile_id: UUID) -> list[Skill]:
        raise NotImplementedError

    async def get_experiences(self, profile_id: UUID) -> list[Experience]:
        raise NotImplementedError

    async def get_experience_by_id(self, exp_id: UUID) -> Experience | None:
        raise NotImplementedError

    async def update_experience(self, exp_id: UUID, data: dict[str, Any]) -> Experience | None:
        raise NotImplementedError

    async def get_bullets(self, experience_id: UUID) -> list[Bullet]:
        raise NotImplementedError

    async def update_bullet(self, bullet_id: UUID, data: dict[str, Any]) -> Bullet | None:
        raise NotImplementedError

    async def delete_bullet(self, bullet_id: UUID) -> bool:
        raise NotImplementedError

    async def get_projects(self, profile_id: UUID) -> list[Project]:
        raise NotImplementedError

    async def get_education(self, profile_id: UUID) -> list[Education]:
        raise NotImplementedError

    async def get_jd_record(self, jd_id: UUID) -> JDRecord | None:
        raise NotImplementedError

    async def list_jd_records(self, user_id: str) -> list[JDRecord]:
        raise NotImplementedError

    async def delete_jd_record(self, jd_id: UUID) -> bool:
        raise NotImplementedError

    async def update_jd_match_score(self, jd_id: UUID, score: float) -> None:
        raise NotImplementedError

    async def save_resume_artifact(self, artifact: ResumeArtifact) -> None:
        raise NotImplementedError

    async def get_resume_artifact(self, artifact_id: UUID) -> ResumeArtifact | None:
        raise NotImplementedError

    async def list_resume_artifacts(self, user_id: str) -> list[ResumeArtifact]:
        raise NotImplementedError

    async def delete_resume_artifact(self, artifact_id: UUID) -> bool:
        raise NotImplementedError

    async def delete_resume_artifacts_by_jd(self, jd_record_id: UUID) -> int:
        raise NotImplementedError

    async def update_resume_artifact(self, artifact_id: UUID, data: dict[str, Any]) -> bool:
        raise NotImplementedError

    # Task methods
    async def save_task(self, task: Task) -> None:
        raise NotImplementedError

    async def get_task(self, task_id: UUID) -> Task | None:
        raise NotImplementedError

    async def update_task(self, task_id: UUID, data: dict[str, Any]) -> Task | None:
        raise NotImplementedError

    async def delete_project(self, project_id: UUID) -> bool:
        raise NotImplementedError

    async def update_project(self, project_id: UUID, data: dict[str, Any]) -> Project | None:
        raise NotImplementedError

    async def delete_experience(self, exp_id: UUID) -> bool:
        raise NotImplementedError

    async def update_skill(self, skill_id: UUID, data: dict[str, Any]) -> Skill | None:
        raise NotImplementedError

    async def delete_skill(self, skill_id: UUID) -> bool:
        raise NotImplementedError

    async def update_education(self, edu_id: UUID, data: dict[str, Any]) -> Education | None:
        raise NotImplementedError

    async def delete_education(self, edu_id: UUID) -> bool:
        raise NotImplementedError

    # Token usage methods
    async def save_token_usage(self, usage: TokenUsage) -> None:
        raise NotImplementedError

    async def get_token_usage_by_workflow(self, workflow_run_id: UUID) -> list[TokenUsage]:
        raise NotImplementedError

    async def get_token_usage_in_range(
        self, user_id: str, start: datetime, end: datetime
    ) -> list[TokenUsage]:
        raise NotImplementedError

    async def get_recent_token_usage(self, user_id: str, limit: int) -> list[TokenUsage]:
        raise NotImplementedError

    # Log methods
    async def save_log_entry(self, entry: Any) -> None:
        raise NotImplementedError

    async def query_logs(
        self,
        category: str | None = None,
        level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Any], int]:
        """Returns (entries, total_count)."""
        raise NotImplementedError

    async def delete_logs(self, older_than_days: int = 0) -> int:
        raise NotImplementedError

    async def get_log_stats(self) -> dict[str, Any]:
        raise NotImplementedError


class InMemoryDataStorage(DataStorage):
    """In-memory storage for testing and development."""

    def __init__(self):
        self._profiles: dict[str, Profile] = {}
        self._skills: dict[UUID, list[Skill]] = {}
        self._experiences: dict[UUID, list[Experience]] = {}
        self._experiences_by_id: dict[UUID, Experience] = {}
        self._bullets: dict[UUID, list[Bullet]] = {}
        self._bullets_by_id: dict[UUID, Bullet] = {}
        self._projects: dict[UUID, list[Project]] = {}
        self._education: dict[UUID, list[Education]] = {}
        self._jd_records: dict[UUID, JDRecord] = {}
        self._resume_artifacts: dict[UUID, ResumeArtifact] = {}
        self._tasks: dict[UUID, Task] = {}
        self._token_usages: list[TokenUsage] = []

    # Profile operations
    async def save_profile(self, profile: Profile) -> None:
        self._profiles[profile.user_id] = profile

    async def get_profile(self, user_id: str) -> Profile | None:
        return self._profiles.get(user_id)

    async def update_profile(self, profile_id: UUID, data: dict[str, Any]) -> Profile | None:
        for uid, p in self._profiles.items():
            if p.id == profile_id:
                updated = p.model_copy(update=data)
                self._profiles[uid] = updated
                return updated
        return None

    # Skills
    async def save_skill(self, skill: Skill) -> None:
        if skill.profile_id not in self._skills:
            self._skills[skill.profile_id] = []
        self._skills[skill.profile_id].append(skill)

    async def get_skills(self, profile_id: UUID) -> list[Skill]:
        return self._skills.get(profile_id, [])

    # Experiences
    async def save_experience(self, exp: Experience) -> None:
        if exp.profile_id not in self._experiences:
            self._experiences[exp.profile_id] = []
        self._experiences[exp.profile_id].append(exp)
        self._experiences_by_id[exp.id] = exp

    async def get_experiences(self, profile_id: UUID) -> list[Experience]:
        return self._experiences.get(profile_id, [])

    async def get_experience_by_id(self, exp_id: UUID) -> Experience | None:
        return self._experiences_by_id.get(exp_id)

    async def update_experience(self, exp_id: UUID, data: dict[str, Any]) -> Experience | None:
        exp = self._experiences_by_id.get(exp_id)
        if not exp:
            return None
        updated = exp.model_copy(update=data)
        self._experiences_by_id[exp_id] = updated
        # Update in profile list too
        if exp.profile_id in self._experiences:
            self._experiences[exp.profile_id] = [
                updated if e.id == exp_id else e
                for e in self._experiences[exp.profile_id]
            ]
        return updated

    # Bullets
    async def save_bullet(self, bullet: Bullet) -> None:
        if bullet.experience_id not in self._bullets:
            self._bullets[bullet.experience_id] = []
        self._bullets[bullet.experience_id].append(bullet)
        self._bullets_by_id[bullet.id] = bullet

    async def get_bullets(self, experience_id: UUID) -> list[Bullet]:
        return self._bullets.get(experience_id, [])

    async def update_bullet(self, bullet_id: UUID, data: dict[str, Any]) -> Bullet | None:
        bullet = self._bullets_by_id.get(bullet_id)
        if not bullet:
            return None
        updated = bullet.model_copy(update=data)
        self._bullets_by_id[bullet_id] = updated
        if bullet.experience_id in self._bullets:
            self._bullets[bullet.experience_id] = [
                updated if b.id == bullet_id else b
                for b in self._bullets[bullet.experience_id]
            ]
        return updated

    async def delete_bullet(self, bullet_id: UUID) -> bool:
        bullet = self._bullets_by_id.pop(bullet_id, None)
        if not bullet:
            return False
        if bullet.experience_id in self._bullets:
            self._bullets[bullet.experience_id] = [
                b for b in self._bullets[bullet.experience_id] if b.id != bullet_id
            ]
        return True

    # Projects
    async def save_project(self, project: Project) -> None:
        if project.profile_id not in self._projects:
            self._projects[project.profile_id] = []
        self._projects[project.profile_id].append(project)

    async def get_projects(self, profile_id: UUID) -> list[Project]:
        return self._projects.get(profile_id, [])

    async def delete_project(self, project_id: UUID) -> bool:
        for pid, projects in self._projects.items():
            for i, p in enumerate(projects):
                if p.id == project_id:
                    projects.pop(i)
                    return True
        return False

    async def update_project(self, project_id: UUID, data: dict[str, Any]) -> Project | None:
        # Coerce experience_id to UUID if present
        if "experience_id" in data and data["experience_id"] is not None:
            data["experience_id"] = UUID(str(data["experience_id"]))
        for pid, projects in self._projects.items():
            for i, p in enumerate(projects):
                if p.id == project_id:
                    updated = p.model_copy(update=data)
                    projects[i] = updated
                    return updated
        return None

    async def delete_experience(self, exp_id: UUID) -> bool:
        exp = self._experiences_by_id.pop(exp_id, None)
        if not exp:
            return False
        if exp.profile_id in self._experiences:
            self._experiences[exp.profile_id] = [
                e for e in self._experiences[exp.profile_id] if e.id != exp_id
            ]
        # Also delete associated bullets
        self._bullets.pop(exp_id, None)
        return True

    async def update_skill(self, skill_id: UUID, data: dict[str, Any]) -> Skill | None:
        for pid, skills in self._skills.items():
            for i, s in enumerate(skills):
                if s.id == skill_id:
                    updated = s.model_copy(update=data)
                    skills[i] = updated
                    return updated
        return None

    async def delete_skill(self, skill_id: UUID) -> bool:
        for pid, skills in self._skills.items():
            for i, s in enumerate(skills):
                if s.id == skill_id:
                    skills.pop(i)
                    return True
        return False

    async def update_education(self, edu_id: UUID, data: dict[str, Any]) -> Education | None:
        for pid, edus in self._education.items():
            for i, e in enumerate(edus):
                if e.id == edu_id:
                    updated = e.model_copy(update=data)
                    edus[i] = updated
                    return updated
        return None

    async def delete_education(self, edu_id: UUID) -> bool:
        for pid, edus in self._education.items():
            for i, e in enumerate(edus):
                if e.id == edu_id:
                    edus.pop(i)
                    return True
        return False

    # Education
    async def save_education(self, edu: Education) -> None:
        if edu.profile_id not in self._education:
            self._education[edu.profile_id] = []
        self._education[edu.profile_id].append(edu)

    async def get_education(self, profile_id: UUID) -> list[Education]:
        return self._education.get(profile_id, [])

    # JD Records
    async def save_jd_record(self, jd: JDRecord) -> None:
        self._jd_records[jd.id] = jd

    async def get_jd_record(self, jd_id: UUID) -> JDRecord | None:
        return self._jd_records.get(jd_id)

    async def list_jd_records(self, user_id: str) -> list[JDRecord]:
        records = [j for j in self._jd_records.values() if j.user_id == user_id]
        records.sort(key=lambda j: j.created_at, reverse=True)
        return records

    async def delete_jd_record(self, jd_id: UUID) -> bool:
        return self._jd_records.pop(jd_id, None) is not None

    async def update_jd_match_score(self, jd_id: UUID, score: float) -> None:
        if jd_id in self._jd_records:
            self._jd_records[jd_id].match_score = score

    # Resume Artifacts
    async def save_resume_artifact(self, artifact: ResumeArtifact) -> None:
        self._resume_artifacts[artifact.id] = artifact

    async def get_resume_artifact(self, artifact_id: UUID) -> ResumeArtifact | None:
        return self._resume_artifacts.get(artifact_id)

    async def list_resume_artifacts(self, user_id: str) -> list[ResumeArtifact]:
        artifacts = [a for a in self._resume_artifacts.values() if a.user_id == user_id]
        artifacts.sort(key=lambda a: a.created_at, reverse=True)
        return artifacts

    async def delete_resume_artifact(self, artifact_id: UUID) -> bool:
        return self._resume_artifacts.pop(artifact_id, None) is not None

    async def delete_resume_artifacts_by_jd(self, jd_record_id: UUID) -> int:
        to_delete = [
            aid for aid, a in self._resume_artifacts.items()
            if a.jd_record_id == jd_record_id
        ]
        for aid in to_delete:
            del self._resume_artifacts[aid]
        return len(to_delete)

    # Resume Artifact update
    async def update_resume_artifact(self, artifact_id: UUID, data: dict[str, Any]) -> bool:
        artifact = self._resume_artifacts.get(artifact_id)
        if not artifact:
            return False
        self._resume_artifacts[artifact_id] = artifact.model_copy(update=data)
        return True

    # Tasks
    async def save_task(self, task: Task) -> None:
        self._tasks[task.id] = task

    async def get_task(self, task_id: UUID) -> Task | None:
        return self._tasks.get(task_id)

    async def update_task(self, task_id: UUID, data: dict[str, Any]) -> Task | None:
        task = self._tasks.get(task_id)
        if not task:
            return None
        updated = task.model_copy(update=data)
        self._tasks[task_id] = updated
        return updated

    # Token Usage
    async def save_token_usage(self, usage: TokenUsage) -> None:
        self._token_usages.append(usage)

    async def get_token_usage_by_workflow(self, workflow_run_id: UUID) -> list[TokenUsage]:
        return [u for u in self._token_usages if u.workflow_run_id == workflow_run_id]

    async def get_token_usage_in_range(
        self, user_id: str, start: datetime, end: datetime
    ) -> list[TokenUsage]:
        return [
            u for u in self._token_usages
            if u.user_id == user_id and start <= u.created_at <= end
        ]

    async def get_recent_token_usage(self, user_id: str, limit: int) -> list[TokenUsage]:
        user_usages = [u for u in self._token_usages if u.user_id == user_id]
        user_usages.sort(key=lambda u: u.created_at, reverse=True)
        return user_usages[:limit]

    # Log entries (in-memory list)
    async def save_log_entry(self, entry: Any) -> None:
        if not hasattr(self, "_log_entries"):
            self._log_entries: list = []
        self._log_entries.append(entry)

    async def query_logs(
        self,
        category: str | None = None,
        level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Any], int]:
        entries = getattr(self, "_log_entries", [])
        filtered = entries
        if category:
            filtered = [e for e in filtered if e.category == category]
        if level:
            filtered = [e for e in filtered if e.level == level]
        filtered.sort(key=lambda e: e.created_at, reverse=True)
        total = len(filtered)
        return filtered[offset : offset + limit], total

    async def delete_logs(self, older_than_days: int = 0) -> int:
        if not hasattr(self, "_log_entries"):
            return 0
        if older_than_days == 0:
            count = len(self._log_entries)
            self._log_entries.clear()
            return count
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        before = len(self._log_entries)
        self._log_entries = [e for e in self._log_entries if e.created_at >= cutoff]
        return before - len(self._log_entries)

    async def get_log_stats(self) -> dict[str, Any]:
        entries = getattr(self, "_log_entries", [])
        by_cat: dict[str, int] = {}
        by_level: dict[str, int] = {}
        total_tokens = 0
        for e in entries:
            by_cat[e.category] = by_cat.get(e.category, 0) + 1
            by_level[e.level] = by_level.get(e.level, 0) + 1
            total_tokens += e.data.get("total_tokens", 0)
        return {
            "total_entries": len(entries),
            "by_category": by_cat,
            "by_level": by_level,
            "total_tokens_used": total_tokens,
            "oldest_entry": entries[-1].created_at.isoformat() if entries else None,
            "newest_entry": entries[0].created_at.isoformat() if entries else None,
        }
