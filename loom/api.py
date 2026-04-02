"""FastAPI application entry point."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()
from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from loom.chat import chat_router
from loom.storage.bullet import Bullet, Confidence
from loom.storage.profile import Education, Experience, Profile, Skill, SkillLevel
from loom.storage.project import Project
from loom.storage.repository import DataStorage, ProfileRepository
from loom.storage.resume import Task

logger = logging.getLogger(__name__)


# Global storage — uses autocommit session per operation
_storage: DataStorage | None = None


def get_storage() -> DataStorage:
    """Get the global PostgreSQL storage instance."""
    global _storage
    if _storage is None:
        from loom.storage.postgres import AutocommitPostgresStorage
        _storage = AutocommitPostgresStorage()
    return _storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    storage = get_storage()
    from loom.chat.router import set_storage
    set_storage(storage)
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info("system", "app.startup", "Loom API server started")
    except Exception:
        pass
    yield


app = FastAPI(
    title="Loom API",
    description="AI-native automation workflow engine API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Log unhandled exceptions."""
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.error(
            "system", "unhandled_exception",
            f"Unhandled error: {str(exc)}",
            error=exc,
            path=str(request.url.path),
            method=request.method,
        )
    except Exception:
        pass
    raise exc

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJSONResponse

LOOM_API_KEY = os.environ.get("LOOM_API_KEY", "")


class AuthMiddleware(BaseHTTPMiddleware):
    """Require Bearer token for ALL external API requests.

    Requests from localhost bypass auth (dashboard proxy / local dev).
    All external requests (GET included) require Bearer token.
    """

    async def dispatch(self, request: StarletteRequest, call_next):
        if request.url.path.startswith("/api/"):
            client_host = request.client.host if request.client else ""
            is_local = client_host in ("127.0.0.1", "::1", "localhost")
            if not is_local:
                auth = request.headers.get("authorization", "")
                if not LOOM_API_KEY or not auth.startswith("Bearer "):
                    return StarletteJSONResponse(
                        {"detail": "Authentication required"}, status_code=401
                    )
                token = auth[7:]
                if token != LOOM_API_KEY:
                    return StarletteJSONResponse(
                        {"detail": "Invalid API key"}, status_code=403
                    )
        return await call_next(request)


class MutationLogMiddleware(BaseHTTPMiddleware):
    """Log all POST/PATCH/DELETE API requests."""

    async def dispatch(self, request: StarletteRequest, call_next):
        if request.method in ("POST", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
            try:
                from loom.services.logger import logger as loom_logger
                await loom_logger.info(
                    "user_action",
                    f"api.{request.method.lower()}",
                    f"{request.method} {request.url.path}",
                    path=request.url.path,
                    method=request.method,
                )
            except Exception:
                pass
        return await call_next(request)


app.add_middleware(MutationLogMiddleware)
app.add_middleware(AuthMiddleware)
app.include_router(chat_router)


# ── Helpers ──────────────────────────────────────────────────


def _parse_date(s: str | None) -> date | None:
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


async def _auto_translate_experience(exp: Experience) -> None:
    """Best-effort auto-translate _zh fields for an experience."""
    try:
        from loom.services.translator import TranslationService
        svc = TranslationService()
        translated = await svc.translate_experience(exp)
        if translated is not exp:
            storage = get_storage()
            updates = {}
            if translated.title_zh and not exp.title_zh:
                updates["title_zh"] = translated.title_zh
            if translated.company_zh and not exp.company_zh:
                updates["company_zh"] = translated.company_zh
            if translated.location_zh and not exp.location_zh:
                updates["location_zh"] = translated.location_zh
            if updates:
                await storage.update_experience(exp.id, updates)
    except Exception:
        logger.debug("Auto-translate experience skipped", exc_info=True)


async def _auto_translate_project(project_id: UUID) -> None:
    """Best-effort auto-translate _zh fields for a project and its bullets."""
    try:
        from loom.services.translator import TranslationService
        svc = TranslationService()
        storage = get_storage()

        # Find the project in storage
        projects_by_profile: dict = storage._projects  # InMemory access
        project = None
        for pid, plist in projects_by_profile.items():
            for p in plist:
                if p.id == project_id:
                    project = p
                    break

        if not project:
            return

        updates: dict[str, Any] = {}

        # Translate text fields
        if project.name_en and project.name_zh == project.name_en:
            zh = await svc.translate_to_zh("project name", project.name_en)
            if zh:
                updates["name_zh"] = zh

        if project.description_en and project.description_zh == project.description_en:
            zh = await svc.translate_to_zh(
                "project description", project.description_en,
                context=f"Project: {project.name_en}",
            )
            if zh:
                updates["description_zh"] = zh

        if project.role_en and project.role_zh == project.role_en:
            zh = await svc.translate_to_zh("project role", project.role_en)
            if zh:
                updates["role_zh"] = zh

        # Translate bullets content_en inside the JSONB list
        if project.bullets:
            translated_bullets = []
            changed = False
            for b in project.bullets:
                en = b.get("content_en", "")
                zh = b.get("content_zh")
                if en and (not zh or zh == en):
                    new_zh = await svc.translate_to_zh(
                        "project bullet", en,
                        context=f"Project: {project.name_en}",
                    )
                    if new_zh:
                        translated_bullets.append({**b, "content_zh": new_zh})
                        changed = True
                        continue
                translated_bullets.append(b)
            if changed:
                updates["bullets"] = translated_bullets

        if updates:
            await storage.update_project(project_id, updates)
    except Exception:
        logger.debug("Auto-translate project skipped", exc_info=True)


# ── Bilingual helper ─────────────────────────────────────────


def _ensure_bilingual(data: dict[str, Any], pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """For each (en_key, zh_key) pair, copy one side to the other if missing."""
    out = dict(data)
    for en_key, zh_key in pairs:
        en_val = out.get(en_key)
        zh_val = out.get(zh_key)
        if en_val and not zh_val:
            out[zh_key] = en_val
        elif zh_val and not en_val:
            out[en_key] = zh_val
    return out


# ══════════════════════════════════════════════════════════════
# Profile basic — GET / POST / PATCH
# ══════════════════════════════════════════════════════════════


class ProfileResponse(BaseModel):
    profile: dict[str, Any] | None
    skills: list[dict[str, Any]]
    experiences: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    education: list[dict[str, Any]]


@app.get("/api/profile", response_model=ProfileResponse)
async def get_profile(user_id: str = "local", lang: str = "en") -> ProfileResponse:
    if lang not in ("en", "zh"):
        raise HTTPException(status_code=400, detail="lang must be 'en' or 'zh'")
    storage = get_storage()
    repo = ProfileRepository(storage)
    full = await repo.get_full_profile(user_id, lang=lang)
    if not full:
        return ProfileResponse(profile=None, skills=[], experiences=[], projects=[], education=[])
    return ProfileResponse(**full)


class CreateProfileRequest(BaseModel):
    name_en: str
    name_zh: str | None = None
    email: str | None = None
    phone: str | None = None
    location_en: str | None = None
    location_zh: str | None = None
    summary_en: str | None = None
    summary_zh: str | None = None


@app.post("/api/profile/basic")
async def create_profile(request: CreateProfileRequest, user_id: str = "local"):
    storage = get_storage()
    existing = await storage.get_profile(user_id)
    if existing:
        raise HTTPException(status_code=409, detail="Profile already exists")
    data = _ensure_bilingual(request.model_dump(), [
        ("name_en", "name_zh"),
        ("location_en", "location_zh"),
        ("summary_en", "summary_zh"),
    ])
    profile = Profile(user_id=user_id, **data)
    await storage.save_profile(profile)
    return {"status": "ok", "id": str(profile.id)}


class PatchBasicRequest(BaseModel):
    field: str
    value: Any
    lang: str = Field(default="en", pattern="^(en|zh)$")


@app.patch("/api/profile/basic")
async def patch_profile_basic(request: PatchBasicRequest, user_id: str = "local"):
    storage = get_storage()
    repo = ProfileRepository(storage)
    profile = await storage.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    bilingual_fields = {"name", "location", "summary", "phone"}
    col = f"{request.field}_{request.lang}" if request.field in bilingual_fields else request.field
    updated = await repo.update_basic_info(profile.id, {col: request.value})
    if not updated:
        raise HTTPException(status_code=400, detail="Update failed")
    return {"status": "ok", "field": col}


# ══════════════════════════════════════════════════════════════
# Experience — POST / PATCH / DELETE
# ══════════════════════════════════════════════════════════════


class CreateExperienceRequest(BaseModel):
    company_en: str
    company_zh: str | None = None
    title_en: str
    title_zh: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    location_en: str | None = None
    location_zh: str | None = None
    is_visible: bool = True


@app.post("/api/profile/experience")
async def create_experience(request: CreateExperienceRequest, user_id: str = "local"):
    storage = get_storage()
    profile = await storage.get_profile(user_id)
    if not profile:
        profile = Profile(name_en=user_id, user_id=user_id)
        await storage.save_profile(profile)

    data = _ensure_bilingual(request.model_dump(), [
        ("company_en", "company_zh"),
        ("title_en", "title_zh"),
        ("location_en", "location_zh"),
    ])
    exp = Experience(
        user_id=user_id,
        profile_id=profile.id,
        company_en=data["company_en"],
        company_zh=data["company_zh"],
        title_en=data["title_en"],
        title_zh=data["title_zh"],
        location_en=data["location_en"],
        location_zh=data["location_zh"],
        start_date=_parse_date(data["start_date"]),
        end_date=_parse_date(data["end_date"]),
        is_visible=data["is_visible"],
    )
    await storage.save_experience(exp)

    # Best-effort auto-translate
    await _auto_translate_experience(exp)

    return {"status": "ok", "id": str(exp.id)}


class PatchExperienceRequest(BaseModel):
    data: dict[str, Any]


@app.patch("/api/profile/experience/{exp_id}")
async def patch_experience(exp_id: UUID, request: PatchExperienceRequest):
    storage = get_storage()
    updated = await storage.update_experience(exp_id, request.data)
    if not updated:
        raise HTTPException(status_code=404, detail="Experience not found")
    return {"status": "ok", "id": str(exp_id)}


@app.delete("/api/profile/experience/{exp_id}")
async def delete_experience(exp_id: UUID):
    storage = get_storage()
    deleted = await storage.delete_experience(exp_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Experience not found")
    return {"status": "ok", "id": str(exp_id)}


# ══════════════════════════════════════════════════════════════
# Bullet — POST / PATCH / DELETE
# ══════════════════════════════════════════════════════════════


class CreateBulletRequest(BaseModel):
    experience_id: UUID
    content_en: str
    content_zh: str | None = None
    raw_text: str | None = None
    star_data: dict[str, Any] = {}
    tech_stack: list[dict[str, Any]] = []
    type: str = "implementation"
    priority: int = 3
    confidence: str = "high"
    missing: list[str] = []
    auto_translate: bool = True


@app.post("/api/profile/bullet")
async def create_bullet(request: CreateBulletRequest):
    storage = get_storage()
    repo = ProfileRepository(storage)

    data = _ensure_bilingual(
        {"content_en": request.content_en, "content_zh": request.content_zh},
        [("content_en", "content_zh")],
    )
    bullet_data: dict[str, Any] = {
        "content_en": data["content_en"],
        "content_zh": data["content_zh"],
        "raw_text": request.raw_text or request.content_en,
        "star_data": request.star_data,
        "tech_stack": request.tech_stack,
        "type": request.type,
        "priority": request.priority,
        "confidence": request.confidence,
        "missing": request.missing,
    }
    bullet = await repo.add_bullet(request.experience_id, bullet_data)

    if request.auto_translate and not request.content_zh:
        try:
            from loom.services.translator import TranslationService
            svc = TranslationService()
            translated = await svc.translate_bullets([bullet])
            if translated and translated[0].content_zh:
                await repo.update_bullet(bullet.id, {"content_zh": translated[0].content_zh})
        except Exception:
            logger.debug("Auto-translate bullet skipped", exc_info=True)

    return {"status": "ok", "id": str(bullet.id)}


class PatchBulletRequest(BaseModel):
    data: dict[str, Any]


@app.patch("/api/profile/bullet/{bullet_id}")
async def patch_bullet(bullet_id: UUID, request: PatchBulletRequest):
    storage = get_storage()
    repo = ProfileRepository(storage)
    data = {**request.data, "confidence": "user_edited"}
    updated = await repo.update_bullet(bullet_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return {"status": "ok", "id": str(bullet_id)}


@app.delete("/api/profile/bullet/{bullet_id}")
async def delete_bullet(bullet_id: UUID):
    storage = get_storage()
    repo = ProfileRepository(storage)
    deleted = await repo.delete_bullet(bullet_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return {"status": "ok", "id": str(bullet_id)}


# ══════════════════════════════════════════════════════════════
# Skill — POST / PATCH / DELETE
# ══════════════════════════════════════════════════════════════


class CreateSkillRequest(BaseModel):
    name: str
    level: str = "proficient"
    category: str | None = None
    context_en: str | None = None
    context_zh: str | None = None


@app.post("/api/profile/skill")
async def create_skill(request: CreateSkillRequest, user_id: str = "local"):
    storage = get_storage()
    profile = await storage.get_profile(user_id)
    if not profile:
        profile = Profile(name_en=user_id, user_id=user_id)
        await storage.save_profile(profile)

    data = _ensure_bilingual(
        {"context_en": request.context_en, "context_zh": request.context_zh},
        [("context_en", "context_zh")],
    )
    skill = Skill(
        user_id=user_id,
        profile_id=profile.id,
        name=request.name,
        level=SkillLevel(request.level),
        category=request.category,
        context_en=data["context_en"],
        context_zh=data["context_zh"],
    )
    await storage.save_skill(skill)
    return {"status": "ok", "id": str(skill.id), "name": skill.name}


class PatchSkillRequest(BaseModel):
    data: dict[str, Any]


@app.patch("/api/profile/skill/{skill_id}")
async def patch_skill(skill_id: UUID, request: PatchSkillRequest):
    storage = get_storage()
    updated = await storage.update_skill(skill_id, request.data)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "ok", "id": str(skill_id)}


@app.delete("/api/profile/skill/{skill_id}")
async def delete_skill(skill_id: UUID):
    storage = get_storage()
    deleted = await storage.delete_skill(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "ok", "id": str(skill_id)}


# ══════════════════════════════════════════════════════════════
# Education — POST / PATCH / DELETE
# ══════════════════════════════════════════════════════════════


class CreateEducationRequest(BaseModel):
    institution_en: str
    institution_zh: str | None = None
    degree_en: str | None = None
    degree_zh: str | None = None
    field_en: str | None = None
    field_zh: str | None = None
    start_date: str | None = None
    end_date: str | None = None


@app.post("/api/profile/education")
async def create_education(request: CreateEducationRequest, user_id: str = "local"):
    storage = get_storage()
    profile = await storage.get_profile(user_id)
    if not profile:
        profile = Profile(name_en=user_id, user_id=user_id)
        await storage.save_profile(profile)

    data = _ensure_bilingual(request.model_dump(), [
        ("institution_en", "institution_zh"),
        ("degree_en", "degree_zh"),
        ("field_en", "field_zh"),
    ])
    edu = Education(
        user_id=user_id,
        profile_id=profile.id,
        institution_en=data["institution_en"],
        institution_zh=data["institution_zh"],
        degree_en=data["degree_en"],
        degree_zh=data["degree_zh"],
        field_en=data["field_en"],
        field_zh=data["field_zh"],
        start_date=_parse_date(data["start_date"]),
        end_date=_parse_date(data["end_date"]),
    )
    await storage.save_education(edu)
    return {"status": "ok", "id": str(edu.id)}


class PatchEducationRequest(BaseModel):
    data: dict[str, Any]


@app.patch("/api/profile/education/{edu_id}")
async def patch_education(edu_id: UUID, request: PatchEducationRequest):
    storage = get_storage()
    updated = await storage.update_education(edu_id, request.data)
    if not updated:
        raise HTTPException(status_code=404, detail="Education not found")
    return {"status": "ok", "id": str(edu_id)}


@app.delete("/api/profile/education/{edu_id}")
async def delete_education(edu_id: UUID):
    storage = get_storage()
    deleted = await storage.delete_education(edu_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Education not found")
    return {"status": "ok", "id": str(edu_id)}


# ══════════════════════════════════════════════════════════════
# Project — POST / PATCH / DELETE
# ══════════════════════════════════════════════════════════════


class CreateProjectRequest(BaseModel):
    name_en: str
    name_zh: str | None = None
    description_en: str | None = None
    description_zh: str | None = None
    role_en: str | None = None
    role_zh: str | None = None
    experience_id: UUID | None = None
    education_id: UUID | None = None
    start_date: str | None = None
    end_date: str | None = None
    tech_stack: list[dict[str, Any]] = []
    bullets: list[dict[str, Any]] = []
    is_visible: bool = True
    local_repo_path: str | None = None


@app.post("/api/profile/project")
async def create_project(request: CreateProjectRequest, user_id: str = "local"):
    storage = get_storage()
    profile = await storage.get_profile(user_id)
    if not profile:
        profile = Profile(name_en=user_id, user_id=user_id)
        await storage.save_profile(profile)

    data = _ensure_bilingual(request.model_dump(), [
        ("name_en", "name_zh"),
        ("description_en", "description_zh"),
        ("role_en", "role_zh"),
    ])
    project = Project(
        user_id=user_id,
        profile_id=profile.id,
        experience_id=request.experience_id,
        education_id=request.education_id,
        name_en=data["name_en"],
        name_zh=data["name_zh"],
        description_en=data["description_en"],
        description_zh=data["description_zh"],
        role_en=data["role_en"],
        role_zh=data["role_zh"],
        start_date=_parse_date(data.get("start_date")),
        end_date=_parse_date(data.get("end_date")),
        tech_stack=data["tech_stack"],
        bullets=data["bullets"],
        is_visible=data["is_visible"],
        local_repo_path=os.path.expanduser(request.local_repo_path) if request.local_repo_path else None,
        last_analyzed_at=datetime.utcnow() if request.local_repo_path else None,
    )
    await storage.save_project(project)
    return {"status": "ok", "id": str(project.id), "name_en": project.name_en}


class PatchProjectRequest(BaseModel):
    data: dict[str, Any]


@app.patch("/api/profile/project/{project_id}")
async def patch_project(project_id: UUID, request: PatchProjectRequest):
    storage = get_storage()
    updated = await storage.update_project(project_id, request.data)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok", "id": str(project_id)}


@app.delete("/api/profile/project/{project_id}")
async def delete_project(project_id: UUID):
    storage = get_storage()
    deleted = await storage.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok", "id": str(project_id)}


# ══════════════════════════════════════════════════════════════
# Resumes — GET list / GET markdown / DELETE
# ══════════════════════════════════════════════════════════════


@app.get("/api/resumes")
async def list_resumes(user_id: str = "local", jd_record_id: str | None = None):
    storage = get_storage()
    artifacts = await storage.list_resume_artifacts(user_id)
    if jd_record_id:
        artifacts = [a for a in artifacts if str(a.jd_record_id) == jd_record_id]

    result = []
    for a in artifacts:
        # Enrich with JD info if available
        jd_company = None
        jd_title = None
        if a.jd_record_id:
            jd = await storage.get_jd_record(a.jd_record_id)
            if jd:
                jd_company = jd.company
                jd_title = jd.title

        result.append({
            "id": str(a.id),
            "jd_record_id": str(a.jd_record_id) if a.jd_record_id else None,
            "jd_company": jd_company,
            "jd_title": jd_title,
            "language": a.language,
            "content_md": a.content_md,
            "content_tex": a.content_tex,
            "has_pdf": bool(a.pdf_path),
            "starred": a.starred,
            "status": a.status or "completed",
            "generation_progress": a.generation_progress,
            "created_at": a.created_at.isoformat(),
            "workflow_run_id": str(a.workflow_run_id) if a.workflow_run_id else None,
        })
    return result


@app.get("/api/resumes/{resume_id}/markdown")
async def download_resume_markdown(resume_id: UUID, user_id: str = "local"):
    storage = get_storage()
    artifact = await storage.get_resume_artifact(resume_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not artifact.content_md:
        raise HTTPException(status_code=404, detail="No markdown content")

    # Build filename
    parts = []
    parts.append(artifact.created_at.strftime("%Y%m%d"))
    if artifact.jd_record_id:
        jd = await storage.get_jd_record(artifact.jd_record_id)
        if jd:
            if jd.company:
                parts.append(jd.company.replace(" ", ""))
            parts.append(jd.title.replace(" ", "-"))
    filename = "-".join(parts) + ".md"

    return Response(
        content=artifact.content_md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/api/resumes/{resume_id}")
async def delete_resume(resume_id: UUID):
    storage = get_storage()
    deleted = await storage.delete_resume_artifact(resume_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"deleted": True}


@app.patch("/api/resumes/{resume_id}/star")
async def toggle_star(resume_id: UUID):
    storage = get_storage()
    artifact = await storage.get_resume_artifact(resume_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Resume not found")
    new_starred = not artifact.starred
    await storage.update_resume_artifact(resume_id, {"starred": new_starred})
    return {"starred": new_starred}


# ══════════════════════════════════════════════════════════════
# Jobs (JD Records) — GET list / DELETE
# ══════════════════════════════════════════════════════════════


@app.get("/api/jobs")
async def list_jobs(user_id: str = "local"):
    storage = get_storage()
    records = await storage.list_jd_records(user_id)

    result = []
    for j in records:
        # Check if a resume exists for this JD
        artifacts = await storage.list_resume_artifacts(user_id)
        has_resume = any(a.jd_record_id == j.id for a in artifacts)

        result.append({
            "id": str(j.id),
            "company": j.company,
            "title": j.title,
            "raw_text": j.raw_text,
            "required_skills": j.required_skills,
            "preferred_skills": j.preferred_skills,
            "key_requirements": j.key_requirements,
            "match_score": j.match_score,
            "has_resume": has_resume,
            "created_at": j.created_at.isoformat(),
        })
    return result


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: UUID):
    storage = get_storage()
    # Cascade: delete associated resume artifacts first
    await storage.delete_resume_artifacts_by_jd(job_id)
    deleted = await storage.delete_jd_record(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}


# ══════════════════════════════════════════════════════════════
# Workflows — GET list / POST run / POST retry
# ══════════════════════════════════════════════════════════════


class WorkflowRunRequest(BaseModel):
    workflow: str
    data: dict[str, Any] = {}


class WorkflowRunResponse(BaseModel):
    workflow_run_id: str
    workflow: str
    status: str


@app.post("/api/workflow/run", response_model=WorkflowRunResponse)
async def run_workflow(request: WorkflowRunRequest) -> WorkflowRunResponse:
    from loom.core import step_registry
    from loom.storage.init_db import get_workflow_definitions
    from loom.triggers import ManualTrigger

    workflows = get_workflow_definitions()
    workflow_def = workflows.get(request.workflow)
    if not workflow_def:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{request.workflow}' not found. Available: {list(workflows.keys())}",
        )

    import loom.steps  # noqa: F401

    trigger = ManualTrigger()
    trigger.set_data(request.data)
    context = await trigger.emit()
    workflow_run_id = context.workflow_id

    storage = get_storage()

    from loom.steps import GenerateResumeStep, MatchProfileStep, ParseJDStep, SelectBulletsStep

    step_classes = {
        "parse-jd": ParseJDStep,
        "match-profile": MatchProfileStep,
        "select-bullets": SelectBulletsStep,
        "generate-resume": GenerateResumeStep,
    }

    try:
        for step_config in sorted(workflow_def.steps, key=lambda s: s.get("order", 0)):
            step_name = step_config["name"]
            step_class = step_classes.get(step_name)
            step = step_class(storage=storage) if step_class else step_registry.get(step_name)
            context = await step.run(context)
    except Exception as e:
        logger.exception("Workflow '%s' failed (run_id=%s)", request.workflow, workflow_run_id)
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {e}")

    return WorkflowRunResponse(
        workflow_run_id=workflow_run_id,
        workflow=request.workflow,
        status="completed",
    )


@app.get("/api/workflows")
async def list_workflows(user_id: str = "local", limit: int = 20):
    """List workflow runs.

    Note: Currently workflow runs are not persisted to storage.
    This endpoint returns an empty list until DB-backed run tracking is added.
    The /api/workflow/run endpoint returns the run_id synchronously for now.
    """
    # TODO: When WorkflowRun persistence is added, query from storage
    return []


@app.post("/api/workflows/{run_id}/retry")
async def retry_workflow(run_id: UUID):
    """Retry a failed workflow run.

    Note: Requires DB-backed workflow run persistence (not yet implemented).
    """
    # TODO: Implement when workflow run persistence is added
    raise HTTPException(
        status_code=501,
        detail="Workflow retry requires persistent run storage (coming soon)",
    )


# ══════════════════════════════════════════════════════════════
# Tasks — async task tracking for JD analysis and resume gen
# ══════════════════════════════════════════════════════════════


class AnalyzeJDRequest(BaseModel):
    jd_text: str


class GenerateResumeRequest(BaseModel):
    jd_record_id: str
    language: str = "en"
    format: str = "markdown"  # markdown / latex / pdf


class TaskResponse(BaseModel):
    task_id: str


async def _run_analyze_jd(task_id: UUID, jd_text: str, storage: DataStorage) -> None:
    """Background coroutine: parse JD + match profile, update task on completion."""
    try:
        await storage.update_task(task_id, {"status": "running"})

        import loom.steps  # noqa: F401
        from loom.steps import MatchProfileStep, ParseJDStep
        from loom.triggers import ManualTrigger

        trigger = ManualTrigger()
        trigger.set_data({"jd_raw_text": jd_text, "language": "en"})
        context = await trigger.emit()

        # Run ParseJD
        parse_step = ParseJDStep(storage=storage)
        context = await parse_step.run(context)

        # Save JDRecord to storage so it appears in /api/jobs
        jd_parsed = context.data.get("jd_parsed", {})
        from loom.storage.resume import JDRecord as JDRecordSchema
        jd_record = JDRecordSchema(
            user_id="local",
            company=jd_parsed.get("company"),
            title=jd_parsed.get("title", "Unknown"),
            raw_text=jd_text,
            required_skills=jd_parsed.get("required_skills", []),
            preferred_skills=jd_parsed.get("preferred_skills", []),
            key_requirements=jd_parsed.get("key_requirements", []),
        )
        await storage.save_jd_record(jd_record)
        jd_record_id = jd_record.id

        # Put jd_record_id into context for MatchProfile to update score
        context = context.model_copy(
            update={"data": {**context.data, "jd_record_id": str(jd_record_id)}}
        )

        # Run MatchProfile
        match_step = MatchProfileStep(storage=storage)
        context = await match_step.run(context)

        match_result = context.data.get("match_result", {})

        output_data = {
            "jd_record_id": str(jd_record_id),
            "company": jd_parsed.get("company"),
            "title": jd_parsed.get("title"),
            "required_skills": jd_parsed.get("required_skills", []),
            "preferred_skills": jd_parsed.get("preferred_skills", []),
            "match_score": match_result.get("score"),
            "matched": match_result.get("matched", []),
            "hard_skill_gaps": match_result.get("hard_skill_gaps", []),
            "reasoning": match_result.get("reasoning", ""),
        }
        await storage.update_task(task_id, {"status": "completed", "output_data": output_data})

    except Exception as e:
        logger.exception("analyze_jd task %s failed", task_id)
        await storage.update_task(task_id, {"status": "failed", "error": str(e)})


STATUS_PERCENT = {
    "matching": 10,
    "selecting": 20,
    "generating": 40,
    "reviewing": 60,
    "scrutiny": 75,
    "compiling": 90,
    "completed": 100,
    "failed": 0,
}


async def _run_generate_resume(
    task_id: UUID,
    jd_record_id: str,
    language: str,
    fmt: str,
    storage: DataStorage,
) -> None:
    """Background coroutine: select bullets + generate resume, optional PDF."""
    placeholder_id: str | None = None
    try:
        await storage.update_task(task_id, {
            "status": "running",
            "output_data": {"progress": {"step": "initializing", "percent": 0}},
        })

        import loom.steps  # noqa: F401
        from loom.steps import GenerateResumeStep, SelectBulletsStep
        from loom.storage.resume import ResumeArtifact as RASchema
        from loom.triggers import ManualTrigger

        jd = await storage.get_jd_record(UUID(jd_record_id))
        if not jd:
            raise ValueError(f"JD record {jd_record_id} not found")

        # Create placeholder resume artifact (visible in UI immediately)
        placeholder = RASchema(
            jd_record_id=UUID(jd_record_id),
            language=language,
            status="matching",
        )
        await storage.save_resume_artifact(placeholder)
        placeholder_id = str(placeholder.id)

        async def _update_status(status: str) -> None:
            await storage.update_resume_artifact(UUID(placeholder_id), {"status": status})
            await storage.update_task(task_id, {
                "output_data": {"progress": {"step": status, "percent": STATUS_PERCENT.get(status, 50)}},
            })

        trigger = ManualTrigger()
        trigger.set_data({
            "jd_raw_text": jd.raw_text,
            "language": language,
            "jd_record_id": str(jd.id),
        })
        context = await trigger.emit()

        context.data["jd_parsed"] = {
            "company": jd.company,
            "title": jd.title,
            "required_skills": jd.required_skills,
            "preferred_skills": jd.preferred_skills,
            "key_requirements": jd.key_requirements,
        }

        # Step 1: Match Profile
        await _update_status("matching")
        from loom.steps import MatchProfileStep
        match_step = MatchProfileStep(storage=storage)
        context = await match_step.run(context)

        # Step 2: Select Bullets
        await _update_status("selecting")
        select_step = SelectBulletsStep(storage=storage)
        context = await select_step.run(context)

        # Step 3: Generate Resume (Phase 1-3b-4 inside)
        await _update_status("generating")
        gen_step = GenerateResumeStep(storage=storage)
        context = await gen_step.run(context)

        resume_artifact_id = context.data.get("resume_artifact_id")
        output_data: dict[str, Any] = {
            "resume_artifact_id": str(resume_artifact_id) if resume_artifact_id else None,
        }

        # Compile LaTeX → PDF
        await storage.update_task(task_id, {
            "output_data": {"progress": {"step": "compiling", "percent": 90}},
        })
        if placeholder_id:
            await storage.update_resume_artifact(UUID(placeholder_id), {"status": "compiling"})
        if resume_artifact_id:
            artifact = await storage.get_resume_artifact(UUID(str(resume_artifact_id)))
            if artifact and artifact.content_tex:
                from loom.services.pdf_generator import PDFGenerator
                generator = PDFGenerator()
                pdf_path = await generator.generate(artifact.content_tex)
                await storage.update_resume_artifact(
                    UUID(str(resume_artifact_id)), {"pdf_path": pdf_path}
                )
                output_data["download_url"] = f"/api/resumes/{resume_artifact_id}/pdf"

        await storage.update_task(task_id, {"status": "completed", "output_data": output_data})

    except Exception as e:
        logger.exception("generate_resume task %s failed", task_id)
        error_msg = str(e)
        if "pdflatex" in error_msg:
            lines = error_msg.split("\n")
            error_msg = "\n".join(lines[-10:])
        await storage.update_task(task_id, {"status": "failed", "error": error_msg})

    finally:
        # Always clean up placeholder
        if placeholder_id:
            try:
                await storage.delete_resume_artifact(UUID(placeholder_id))
            except Exception:
                pass


@app.post("/api/tasks/analyze-jd", response_model=TaskResponse)
async def analyze_jd(request: AnalyzeJDRequest, user_id: str = "local") -> TaskResponse:
    storage = get_storage()
    task = Task(type="analyze_jd", status="pending", input_data={"jd_text": request.jd_text}, user_id=user_id)
    await storage.save_task(task)
    asyncio.create_task(_run_analyze_jd(task.id, request.jd_text, storage))
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info("user_action", "jd.analyze",
            f"Analyzing JD ({len(request.jd_text)} chars)", task_id=str(task.id))
    except Exception:
        pass
    return TaskResponse(task_id=str(task.id))


@app.post("/api/tasks/generate-resume", response_model=TaskResponse)
async def generate_resume_task(request: GenerateResumeRequest, user_id: str = "local") -> TaskResponse:
    storage = get_storage()
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info("user_action", "resume.generate",
            f"Generating resume for JD {request.jd_record_id}",
            jd_record_id=request.jd_record_id, language=request.language)
    except Exception:
        pass
    task = Task(
        type="generate_resume",
        status="pending",
        input_data={
            "jd_record_id": request.jd_record_id,
            "language": request.language,
            "format": request.format,
        },
        user_id=user_id,
    )
    await storage.save_task(task)
    asyncio.create_task(_run_generate_resume(
        task.id, request.jd_record_id, request.language, request.format, storage
    ))
    return TaskResponse(task_id=str(task.id))


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: UUID):
    storage = get_storage()
    task = await storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": str(task.id),
        "type": task.type,
        "status": task.status,
        "output_data": task.output_data if task.status in ("completed", "running") else None,
        "error": task.error if task.status == "failed" else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


# ══════════════════════════════════════════════════════════════
# Resume PDF download
# ══════════════════════════════════════════════════════════════


@app.get("/api/resumes/{resume_id}/pdf")
async def download_resume_pdf(resume_id: UUID, user_id: str = "local"):
    import os

    storage = get_storage()
    artifact = await storage.get_resume_artifact(resume_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Resume not found")

    pdf_path = artifact.pdf_path

    # If no pre-compiled PDF, compile on the fly
    if not pdf_path or not os.path.exists(pdf_path):
        if not artifact.content_tex:
            raise HTTPException(status_code=404, detail="No LaTeX content to compile")
        from loom.services.pdf_generator import PDFGenerator
        generator = PDFGenerator()
        pdf_path = await generator.generate(artifact.content_tex)
        await storage.update_resume_artifact(resume_id, {"pdf_path": pdf_path})

    # Build filename
    parts = [artifact.created_at.strftime("%Y%m%d")]
    if artifact.jd_record_id:
        jd = await storage.get_jd_record(artifact.jd_record_id)
        if jd:
            if jd.company:
                parts.append(jd.company.replace(" ", ""))
            parts.append(jd.title.replace(" ", "-"))
    filename = "-".join(parts) + ".pdf"

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════════
# Logs
# ══════════════════════════════════════════════════════════════


@app.get("/api/logs")
async def list_logs(
    category: str | None = None,
    level: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    storage = get_storage()
    entries, total = await storage.query_logs(
        category=category, level=level, search=search, limit=limit, offset=offset,
    )
    return {"total": total, "entries": entries}


@app.delete("/api/logs/clear")
async def clear_logs(older_than_days: int = 0):
    storage = get_storage()
    deleted = await storage.delete_logs(older_than_days)
    return {"deleted": deleted}


@app.get("/api/logs/stats")
async def log_stats():
    storage = get_storage()
    return await storage.get_log_stats()


# ══════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("LOOM_API_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
