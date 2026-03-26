"""Repository layer for data access."""

from typing import Any
from uuid import UUID

from loom.storage.base import BaseEntity
from loom.storage.bullet import Bullet
from loom.storage.profile import Education, Experience, Profile, Skill
from loom.storage.project import Project
from loom.storage.resume import JDRecord


class ProfileRepository:
    """Repository for fetching profile data.

    Provides methods to get complete profile with all related data
    for matching against job descriptions.
    """

    def __init__(self, storage: "DataStorage | None" = None):
        self.storage = storage or InMemoryDataStorage()

    async def get_full_profile(self, user_id: str = "local") -> dict[str, Any] | None:
        """Get complete profile with skills, experiences, bullets, projects.

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

        # Fetch bullets for each experience
        experiences_with_bullets = []
        for exp in experiences:
            bullets = await self.storage.get_bullets(exp.id)
            experiences_with_bullets.append({
                "id": str(exp.id),
                "company": exp.company,
                "title": exp.title,
                "location": exp.location,
                "start_date": str(exp.start_date) if exp.start_date else None,
                "end_date": str(exp.end_date) if exp.end_date else None,
                "is_visible": exp.is_visible,
                "bullets": [
                    {
                        "raw_text": b.raw_text,
                        "star_data": b.star_data,
                        "type": b.type.value,
                        "tech_stack": b.tech_stack,
                    }
                    for b in bullets if b.is_visible
                ],
            })

        return {
            "profile": {
                "id": str(profile.id),
                "name": profile.name,
                "email": profile.email,
                "phone": profile.phone,
                "location": profile.location,
                "summary": profile.summary,
            },
            "skills": [
                {
                    "name": s.name,
                    "level": s.level.value,
                    "context": s.context,
                }
                for s in skills
            ],
            "experiences": experiences_with_bullets,
            "projects": [
                {
                    "name": p.name,
                    "description": p.description,
                    "role": p.role,
                    "tech_stack": p.tech_stack,
                    "bullets": p.bullets,
                }
                for p in projects if p.is_visible
            ],
            "education": [
                {
                    "institution": e.institution,
                    "degree": e.degree,
                    "field": e.field,
                    "start_date": str(e.start_date) if e.start_date else None,
                    "end_date": str(e.end_date) if e.end_date else None,
                }
                for e in education
            ],
        }


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


class DataStorage:
    """Abstract interface for data persistence."""

    async def get_profile(self, user_id: str) -> Profile | None:
        raise NotImplementedError

    async def get_skills(self, profile_id: UUID) -> list[Skill]:
        raise NotImplementedError

    async def get_experiences(self, profile_id: UUID) -> list[Experience]:
        raise NotImplementedError

    async def get_bullets(self, experience_id: UUID) -> list[Bullet]:
        raise NotImplementedError

    async def get_projects(self, profile_id: UUID) -> list[Project]:
        raise NotImplementedError

    async def get_education(self, profile_id: UUID) -> list[Education]:
        raise NotImplementedError

    async def get_jd_record(self, jd_id: UUID) -> JDRecord | None:
        raise NotImplementedError

    async def update_jd_match_score(self, jd_id: UUID, score: float) -> None:
        raise NotImplementedError


class InMemoryDataStorage(DataStorage):
    """In-memory storage for testing and development."""

    def __init__(self):
        self._profiles: dict[str, Profile] = {}
        self._skills: dict[UUID, list[Skill]] = {}
        self._experiences: dict[UUID, list[Experience]] = {}
        self._bullets: dict[UUID, list[Bullet]] = {}
        self._projects: dict[UUID, list[Project]] = {}
        self._education: dict[UUID, list[Education]] = {}
        self._jd_records: dict[UUID, JDRecord] = {}

    # Profile operations
    async def save_profile(self, profile: Profile) -> None:
        self._profiles[profile.user_id] = profile

    async def get_profile(self, user_id: str) -> Profile | None:
        return self._profiles.get(user_id)

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

    async def get_experiences(self, profile_id: UUID) -> list[Experience]:
        return self._experiences.get(profile_id, [])

    # Bullets
    async def save_bullet(self, bullet: Bullet) -> None:
        if bullet.experience_id not in self._bullets:
            self._bullets[bullet.experience_id] = []
        self._bullets[bullet.experience_id].append(bullet)

    async def get_bullets(self, experience_id: UUID) -> list[Bullet]:
        return self._bullets.get(experience_id, [])

    # Projects
    async def save_project(self, project: Project) -> None:
        if project.profile_id not in self._projects:
            self._projects[project.profile_id] = []
        self._projects[project.profile_id].append(project)

    async def get_projects(self, profile_id: UUID) -> list[Project]:
        return self._projects.get(profile_id, [])

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

    async def update_jd_match_score(self, jd_id: UUID, score: float) -> None:
        if jd_id in self._jd_records:
            self._jd_records[jd_id].match_score = score
