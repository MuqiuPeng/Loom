"""JSON file-backed persistent storage.

Wraps InMemoryDataStorage with automatic save/load to a JSON file.
Every write operation triggers a flush to disk. On init, restores
from the file if it exists.

Zero dependencies beyond stdlib + pydantic.
"""

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from loom.storage.bullet import Bullet
from loom.storage.profile import Education, Experience, Profile, Skill
from loom.storage.project import Project
from loom.storage.repository import InMemoryDataStorage
from loom.storage.resume import JDRecord, ResumeArtifact, Task
from loom.storage.usage import TokenUsage

logger = logging.getLogger(__name__)

# Default storage path
DEFAULT_PATH = Path.home() / ".loom" / "data.json"


def _serialize_uuid_keys(d: dict) -> dict:
    """Convert UUID keys to strings for JSON serialization."""
    return {str(k): v for k, v in d.items()}


def _entity_to_dict(entity: Any) -> dict:
    """Serialize a Pydantic BaseEntity to a JSON-safe dict."""
    d = entity.model_dump(mode="json")
    return d


class JsonFileDataStorage(InMemoryDataStorage):
    """InMemoryDataStorage with JSON file persistence."""

    def __init__(self, path: Path | str | None = None):
        super().__init__()
        self._path = Path(path) if path else DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        """Restore state from JSON file."""
        if not self._path.exists():
            logger.info("No data file at %s, starting fresh", self._path)
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load %s: %s — starting fresh", self._path, e)
            return

        # Restore profiles
        for uid, pdata in raw.get("profiles", {}).items():
            self._profiles[uid] = Profile(**pdata)

        # Restore skills
        for pid_str, skill_list in raw.get("skills", {}).items():
            pid = UUID(pid_str)
            self._skills[pid] = [Skill(**s) for s in skill_list]

        # Restore experiences
        for pid_str, exp_list in raw.get("experiences", {}).items():
            pid = UUID(pid_str)
            exps = [Experience(**e) for e in exp_list]
            self._experiences[pid] = exps
            for exp in exps:
                self._experiences_by_id[exp.id] = exp

        # Restore bullets
        for eid_str, bullet_list in raw.get("bullets", {}).items():
            eid = UUID(eid_str)
            bullets = [Bullet(**b) for b in bullet_list]
            self._bullets[eid] = bullets
            for b in bullets:
                self._bullets_by_id[b.id] = b

        # Restore projects
        for pid_str, proj_list in raw.get("projects", {}).items():
            pid = UUID(pid_str)
            self._projects[pid] = [Project(**p) for p in proj_list]

        # Restore education
        for pid_str, edu_list in raw.get("education", {}).items():
            pid = UUID(pid_str)
            self._education[pid] = [Education(**e) for e in edu_list]

        # Restore JD records
        for jid_str, jdata in raw.get("jd_records", {}).items():
            jid = UUID(jid_str)
            self._jd_records[jid] = JDRecord(**jdata)

        # Restore resume artifacts
        for aid_str, adata in raw.get("resume_artifacts", {}).items():
            aid = UUID(aid_str)
            self._resume_artifacts[aid] = ResumeArtifact(**adata)

        counts = (
            f"{len(self._profiles)} profiles, "
            f"{sum(len(v) for v in self._skills.values())} skills, "
            f"{sum(len(v) for v in self._experiences.values())} experiences, "
            f"{sum(len(v) for v in self._projects.values())} projects"
        )
        logger.info("Loaded from %s: %s", self._path, counts)

    def _flush(self) -> None:
        """Persist current state to JSON file."""
        data = {
            "profiles": {
                uid: _entity_to_dict(p)
                for uid, p in self._profiles.items()
            },
            "skills": {
                str(pid): [_entity_to_dict(s) for s in slist]
                for pid, slist in self._skills.items()
            },
            "experiences": {
                str(pid): [_entity_to_dict(e) for e in elist]
                for pid, elist in self._experiences.items()
            },
            "bullets": {
                str(eid): [_entity_to_dict(b) for b in blist]
                for eid, blist in self._bullets.items()
            },
            "projects": {
                str(pid): [_entity_to_dict(p) for p in plist]
                for pid, plist in self._projects.items()
            },
            "education": {
                str(pid): [_entity_to_dict(e) for e in elist]
                for pid, elist in self._education.items()
            },
            "jd_records": {
                str(jid): _entity_to_dict(j)
                for jid, j in self._jd_records.items()
            },
            "resume_artifacts": {
                str(aid): _entity_to_dict(a)
                for aid, a in self._resume_artifacts.items()
            },
        }

        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    # Override every write method to flush after mutation

    async def save_profile(self, profile: Profile) -> None:
        await super().save_profile(profile)
        self._flush()

    async def update_profile(self, profile_id: UUID, data: dict[str, Any]) -> Profile | None:
        result = await super().update_profile(profile_id, data)
        if result:
            self._flush()
        return result

    async def save_skill(self, skill: Skill) -> None:
        await super().save_skill(skill)
        self._flush()

    async def update_skill(self, skill_id: UUID, data: dict[str, Any]) -> Skill | None:
        result = await super().update_skill(skill_id, data)
        if result:
            self._flush()
        return result

    async def delete_skill(self, skill_id: UUID) -> bool:
        result = await super().delete_skill(skill_id)
        if result:
            self._flush()
        return result

    async def save_experience(self, exp: Experience) -> None:
        await super().save_experience(exp)
        self._flush()

    async def update_experience(self, exp_id: UUID, data: dict[str, Any]) -> Experience | None:
        result = await super().update_experience(exp_id, data)
        if result:
            self._flush()
        return result

    async def delete_experience(self, exp_id: UUID) -> bool:
        result = await super().delete_experience(exp_id)
        if result:
            self._flush()
        return result

    async def save_bullet(self, bullet: Bullet) -> None:
        await super().save_bullet(bullet)
        self._flush()

    async def update_bullet(self, bullet_id: UUID, data: dict[str, Any]) -> Bullet | None:
        result = await super().update_bullet(bullet_id, data)
        if result:
            self._flush()
        return result

    async def delete_bullet(self, bullet_id: UUID) -> bool:
        result = await super().delete_bullet(bullet_id)
        if result:
            self._flush()
        return result

    async def save_project(self, project: Project) -> None:
        await super().save_project(project)
        self._flush()

    async def update_project(self, project_id: UUID, data: dict[str, Any]) -> Project | None:
        result = await super().update_project(project_id, data)
        if result:
            self._flush()
        return result

    async def delete_project(self, project_id: UUID) -> bool:
        result = await super().delete_project(project_id)
        if result:
            self._flush()
        return result

    async def save_education(self, edu: Education) -> None:
        await super().save_education(edu)
        self._flush()

    async def update_education(self, edu_id: UUID, data: dict[str, Any]) -> Education | None:
        result = await super().update_education(edu_id, data)
        if result:
            self._flush()
        return result

    async def delete_education(self, edu_id: UUID) -> bool:
        result = await super().delete_education(edu_id)
        if result:
            self._flush()
        return result

    async def save_jd_record(self, jd: JDRecord) -> None:
        await super().save_jd_record(jd)
        self._flush()

    async def delete_jd_record(self, jd_id: UUID) -> bool:
        result = await super().delete_jd_record(jd_id)
        if result:
            self._flush()
        return result

    async def update_jd_match_score(self, jd_id: UUID, score: float) -> None:
        await super().update_jd_match_score(jd_id, score)
        self._flush()

    async def save_resume_artifact(self, artifact: ResumeArtifact) -> None:
        await super().save_resume_artifact(artifact)
        self._flush()

    async def delete_resume_artifact(self, artifact_id: UUID) -> bool:
        result = await super().delete_resume_artifact(artifact_id)
        if result:
            self._flush()
        return result

    async def delete_resume_artifacts_by_jd(self, jd_record_id: UUID) -> int:
        count = await super().delete_resume_artifacts_by_jd(jd_record_id)
        if count:
            self._flush()
        return count

    async def update_resume_artifact(self, artifact_id: UUID, data: dict[str, Any]) -> bool:
        result = await super().update_resume_artifact(artifact_id, data)
        if result:
            self._flush()
        return result

    async def save_task(self, task: Task) -> None:
        await super().save_task(task)
        # Tasks are ephemeral — no flush needed

    async def update_task(self, task_id: UUID, data: dict[str, Any]) -> Task | None:
        return await super().update_task(task_id, data)
        # Tasks are ephemeral — no flush needed

    async def save_token_usage(self, usage: TokenUsage) -> None:
        await super().save_token_usage(usage)
        self._flush()
