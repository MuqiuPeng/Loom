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

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from loom.chat import chat_router
from loom.current_user import set_current_user
from loom.deps import USER_HEADER, CurrentUser, OwnerOnly
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
    # Daily job-tracker scheduler (10:00 Australia/Sydney)
    from loom.services.job_watcher import daily_scheduler_loop
    scheduler_task = asyncio.create_task(daily_scheduler_loop())
    # Hourly reply poller. The outreach signature undertakes to remove someone
    # from all marketing email within five business days of their asking, and
    # that is only true if something reads the mailbox unprompted.
    from loom.services.replies import poll_loop
    reply_task = asyncio.create_task(poll_loop())
    yield
    scheduler_task.cancel()
    reply_task.cancel()
    from loom.services.google import close_http_client
    await close_http_client()


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
    """Require Bearer token for ALL API requests.

    Every request to /api/ must carry a valid Authorization: Bearer <key>.
    No localhost bypass — cloudflared makes all tunnel traffic appear local.
    """

    async def dispatch(self, request: StarletteRequest, call_next):
        # Bind before anything downstream runs, so logging from middleware and
        # from routes that take no user_id still attributes correctly.
        set_current_user(request.headers.get(USER_HEADER) or "")
        # Signed PDF links (used in Notion) carry their own per-artifact
        # signature validated in the route; exempt them from Bearer auth.
        import re as _re
        if request.method == "GET" and _re.fullmatch(
            r"/api/resumes/[0-9a-f-]+/pdf", request.url.path
        ):
            return await call_next(request)
        if request.url.path.startswith("/api/") and request.url.path != "/api/health":
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
        response = await call_next(request)
        # Profile changed → schedule debounced Notion sync
        if (
            request.method in ("POST", "PATCH", "DELETE")
            and request.url.path.startswith("/api/profile")
            and not request.url.path.endswith("/sync-notion")
            and response.status_code < 400
        ):
            try:
                from loom.services.notion_sync import schedule_sync
                schedule_sync()
            except Exception:
                logger.debug("Notion sync scheduling failed", exc_info=True)
        return response


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
                # The row was just created for this user; scope the write
                # to them so the trusted-caller path stays out of the API layer.
                await storage.update_experience(exp.id, updates, user_id=exp.user_id)
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
async def get_profile(user_id: str = CurrentUser, lang: str = "en") -> ProfileResponse:
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
async def create_profile(request: CreateProfileRequest, user_id: str = CurrentUser):
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
async def patch_profile_basic(request: PatchBasicRequest, user_id: str = CurrentUser):
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
async def create_experience(request: CreateExperienceRequest, user_id: str = CurrentUser):
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
async def patch_experience(
    exp_id: UUID, request: PatchExperienceRequest, user_id: str = CurrentUser
):
    storage = get_storage()
    updated = await storage.update_experience(exp_id, request.data, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Experience not found")
    return {"status": "ok", "id": str(exp_id)}


@app.delete("/api/profile/experience/{exp_id}")
async def delete_experience(exp_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    deleted = await storage.delete_experience(exp_id, user_id=user_id)
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
async def create_bullet(request: CreateBulletRequest, user_id: str = CurrentUser):
    storage = get_storage()
    repo = ProfileRepository(storage)

    # The bullet hangs off an experience, so the experience is what has to be
    # yours — otherwise a guessed UUID would let you write into someone else's
    # history.
    parent = await storage.get_experience_by_id(request.experience_id, user_id=user_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Experience not found")

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
    bullet = await repo.add_bullet(request.experience_id, bullet_data, user_id=user_id)

    if request.auto_translate and not request.content_zh:
        try:
            from loom.services.translator import TranslationService
            svc = TranslationService()
            translated = await svc.translate_bullets([bullet])
            if translated and translated[0].content_zh:
                await repo.update_bullet(
                    bullet.id, {"content_zh": translated[0].content_zh}, user_id=user_id
                )
        except Exception:
            logger.debug("Auto-translate bullet skipped", exc_info=True)

    return {"status": "ok", "id": str(bullet.id)}


class PatchBulletRequest(BaseModel):
    data: dict[str, Any]


@app.patch("/api/profile/bullet/{bullet_id}")
async def patch_bullet(
    bullet_id: UUID, request: PatchBulletRequest, user_id: str = CurrentUser
):
    storage = get_storage()
    repo = ProfileRepository(storage)
    data = {**request.data, "confidence": "high"}
    updated = await repo.update_bullet(bullet_id, data, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return {"status": "ok", "id": str(bullet_id)}


@app.delete("/api/profile/bullet/{bullet_id}")
async def delete_bullet(bullet_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    repo = ProfileRepository(storage)
    deleted = await repo.delete_bullet(bullet_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return {"status": "ok", "id": str(bullet_id)}


# ══════════════════════════════════════════════════════════════
# Notion sync
# ══════════════════════════════════════════════════════════════


@app.post("/api/profile/sync-notion")
async def sync_notion_now(owner: str = OwnerOnly):
    """Manually trigger an immediate profile → Notion sync."""
    from loom.services.notion_sync import _enabled, sync_profile_to_notion

    if not _enabled():
        raise HTTPException(
            status_code=400,
            detail="Notion sync not configured: set NOTION_TOKEN and NOTION_PARENT_PAGE_ID",
        )
    try:
        url = await sync_profile_to_notion(get_storage())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Notion sync failed: {e}")
    return {"status": "ok", "url": url}


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
async def create_skill(request: CreateSkillRequest, user_id: str = CurrentUser):
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
async def patch_skill(
    skill_id: UUID, request: PatchSkillRequest, user_id: str = CurrentUser
):
    storage = get_storage()
    updated = await storage.update_skill(skill_id, request.data, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "ok", "id": str(skill_id)}


@app.delete("/api/profile/skill/{skill_id}")
async def delete_skill(skill_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    deleted = await storage.delete_skill(skill_id, user_id=user_id)
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
async def create_education(request: CreateEducationRequest, user_id: str = CurrentUser):
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
async def patch_education(
    edu_id: UUID, request: PatchEducationRequest, user_id: str = CurrentUser
):
    storage = get_storage()
    updated = await storage.update_education(edu_id, request.data, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Education not found")
    return {"status": "ok", "id": str(edu_id)}


@app.delete("/api/profile/education/{edu_id}")
async def delete_education(edu_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    deleted = await storage.delete_education(edu_id, user_id=user_id)
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
async def create_project(request: CreateProjectRequest, user_id: str = CurrentUser):
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
async def patch_project(
    project_id: UUID, request: PatchProjectRequest, user_id: str = CurrentUser
):
    storage = get_storage()
    updated = await storage.update_project(project_id, request.data, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok", "id": str(project_id)}


@app.delete("/api/profile/project/{project_id}")
async def delete_project(project_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    deleted = await storage.delete_project(project_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok", "id": str(project_id)}


# ══════════════════════════════════════════════════════════════
# Resumes — GET list / GET markdown / DELETE
# ══════════════════════════════════════════════════════════════


@app.get("/api/resumes")
async def list_resumes(user_id: str = CurrentUser, jd_record_id: str | None = None):
    storage = get_storage()
    artifacts = await storage.list_resume_artifacts(user_id)
    if jd_record_id:
        artifacts = [a for a in artifacts if str(a.jd_record_id) == jd_record_id]

    # One query for every JD this user has, rather than one per artifact.
    # Same reason as /api/jobs: a storage call is a round trip, and 146
    # resumes were making 146 of them to label a list.
    jds = {j.id: j for j in await storage.list_jd_records(user_id)}

    result = []
    for a in artifacts:
        # Enrich with JD info if available
        jd_company = None
        jd_title = None
        if a.jd_record_id:
            jd = jds.get(a.jd_record_id)
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
async def download_resume_markdown(resume_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    artifact = await storage.get_resume_artifact(resume_id, user_id=user_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not artifact.content_md:
        raise HTTPException(status_code=404, detail="No markdown content")

    # Build filename
    parts = []
    parts.append(artifact.created_at.strftime("%Y%m%d"))
    if artifact.jd_record_id:
        jd = await storage.get_jd_record(artifact.jd_record_id, user_id=user_id)
        if jd:
            if jd.company:
                parts.append(jd.company.replace(" ", ""))
            parts.append(jd.title.replace(" ", "-"))
    filename = "-".join(parts) + ".md"
    filename = filename.encode("ascii", "ignore").decode("ascii")

    return Response(
        content=artifact.content_md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/api/resumes/{resume_id}")
async def delete_resume(resume_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    deleted = await storage.delete_resume_artifact(resume_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"deleted": True}


@app.patch("/api/resumes/{resume_id}/star")
async def toggle_star(resume_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    artifact = await storage.get_resume_artifact(resume_id, user_id=user_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Resume not found")
    new_starred = not artifact.starred
    await storage.update_resume_artifact(
        resume_id, {"starred": new_starred}, user_id=user_id
    )
    return {"starred": new_starred}


# ══════════════════════════════════════════════════════════════
# Jobs (JD Records) — GET list / DELETE
# ══════════════════════════════════════════════════════════════


@app.get("/api/jobs")
async def list_jobs(user_id: str = CurrentUser):
    storage = get_storage()
    records = await storage.list_jd_records(user_id)
    # Fetched once, not once per job. Each storage call opens its own session,
    # so the old placement made this endpoint do one full artifact scan per JD
    # — 67 round trips to a pooled Postgres to answer one question that the
    # first trip had already answered.
    artifacts = await storage.list_resume_artifacts(user_id)
    jds_with_resumes = {a.jd_record_id for a in artifacts}

    result = []
    for j in records:
        has_resume = j.id in jds_with_resumes

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
async def delete_job(job_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    # Cascade: delete associated resume artifacts first
    await storage.delete_resume_artifacts_by_jd(job_id, user_id=user_id)
    deleted = await storage.delete_jd_record(job_id, user_id=user_id)
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
async def list_workflows(user_id: str = CurrentUser, limit: int = 20):
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


class GenerateGenericResumeRequest(BaseModel):
    language: str = "en"
    format: str = "markdown"  # markdown / latex / pdf
    focus: str | None = None  # optional positioning override, e.g. "Backend Engineer"


class TaskResponse(BaseModel):
    task_id: str


async def _run_analyze_jd(
    task_id: UUID, jd_text: str, storage: DataStorage, user_id: str
) -> None:
    """Background coroutine: parse JD + match profile, update task on completion."""
    try:
        await storage.update_task(task_id, {"status": "running"}, user_id=user_id)

        import loom.steps  # noqa: F401
        from loom.steps import MatchProfileStep, ParseJDStep
        from loom.triggers import ManualTrigger

        trigger = ManualTrigger(user_id=user_id)
        trigger.set_data({"jd_raw_text": jd_text, "language": "en"})
        context = await trigger.emit()

        # Run ParseJD
        parse_step = ParseJDStep(storage=storage)
        context = await parse_step.run(context)

        # Save JDRecord to storage so it appears in /api/jobs
        jd_parsed = context.data.get("jd_parsed", {})
        from loom.storage.resume import JDRecord as JDRecordSchema
        jd_record = JDRecordSchema(
            user_id=user_id,
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
        await storage.update_task(
            task_id, {"status": "completed", "output_data": output_data}, user_id=user_id
        )

    except Exception as e:
        logger.exception("analyze_jd task %s failed", task_id)
        await storage.update_task(
            task_id, {"status": "failed", "error": str(e)}, user_id=user_id
        )


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
    user_id: str,
) -> None:
    """Background coroutine: select bullets + generate resume, optional PDF."""
    placeholder_id: str | None = None
    try:
        await storage.update_task(task_id, {
            "status": "running",
            "output_data": {"progress": {"step": "initializing", "percent": 0}},
        }, user_id=user_id)

        import loom.steps  # noqa: F401
        from loom.steps import GenerateResumeStep, SelectBulletsStep
        from loom.storage.resume import ResumeArtifact as RASchema
        from loom.triggers import ManualTrigger

        jd = await storage.get_jd_record(UUID(jd_record_id), user_id=user_id)
        if not jd:
            raise ValueError(f"JD record {jd_record_id} not found")

        # Create placeholder resume artifact (visible in UI immediately)
        placeholder = RASchema(
            user_id=user_id,
            jd_record_id=UUID(jd_record_id),
            language=language,
            status="matching",
        )
        await storage.save_resume_artifact(placeholder)
        placeholder_id = str(placeholder.id)

        async def _update_status(status: str) -> None:
            await storage.update_resume_artifact(
                UUID(placeholder_id), {"status": status}, user_id=user_id
            )
            await storage.update_task(task_id, {
                "output_data": {"progress": {"step": status, "percent": STATUS_PERCENT.get(status, 50)}},
            }, user_id=user_id)

        trigger = ManualTrigger(user_id=user_id)
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

        # Compile LaTeX → PDF (best-effort: the md/tex artifact is already
        # saved, so a missing pdflatex must not fail the whole task)
        await storage.update_task(task_id, {
            "output_data": {"progress": {"step": "compiling", "percent": 90}},
        }, user_id=user_id)
        if placeholder_id:
            await storage.update_resume_artifact(
                UUID(placeholder_id), {"status": "compiling"}, user_id=user_id
            )
        if resume_artifact_id:
            artifact = await storage.get_resume_artifact(
                UUID(str(resume_artifact_id)), user_id=user_id
            )
            if artifact and artifact.content_tex:
                try:
                    from loom.services.pdf_generator import PDFGenerator
                    generator = PDFGenerator()
                    pdf_path = await generator.generate(artifact.content_tex)
                    await storage.update_resume_artifact(
                        UUID(str(resume_artifact_id)), {"pdf_path": pdf_path},
                        user_id=user_id,
                    )
                    output_data["download_url"] = f"/api/resumes/{resume_artifact_id}/pdf"
                except Exception as pdf_err:
                    logger.warning("PDF compilation skipped: %s", pdf_err)
                    output_data["pdf_error"] = str(pdf_err).split("\n")[0]

        await storage.update_task(
            task_id, {"status": "completed", "output_data": output_data}, user_id=user_id
        )

    except Exception as e:
        logger.exception("generate_resume task %s failed", task_id)
        error_msg = str(e)
        if "pdflatex" in error_msg:
            lines = error_msg.split("\n")
            error_msg = "\n".join(lines[-10:])
        await storage.update_task(
            task_id, {"status": "failed", "error": error_msg}, user_id=user_id
        )

    finally:
        # Always clean up placeholder
        if placeholder_id:
            try:
                await storage.delete_resume_artifact(
                    UUID(placeholder_id), user_id=user_id
                )
            except Exception:
                pass


@app.post("/api/tasks/analyze-jd", response_model=TaskResponse)
async def analyze_jd(request: AnalyzeJDRequest, user_id: str = CurrentUser) -> TaskResponse:
    storage = get_storage()
    task = Task(type="analyze_jd", status="pending", input_data={"jd_text": request.jd_text}, user_id=user_id)
    await storage.save_task(task)
    asyncio.create_task(_run_analyze_jd(task.id, request.jd_text, storage, user_id))
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info("user_action", "jd.analyze",
            f"Analyzing JD ({len(request.jd_text)} chars)", task_id=str(task.id))
    except Exception:
        pass
    return TaskResponse(task_id=str(task.id))


@app.post("/api/tasks/generate-resume", response_model=TaskResponse)
async def generate_resume_task(request: GenerateResumeRequest, user_id: str = CurrentUser) -> TaskResponse:
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
        task.id, request.jd_record_id, request.language, request.format, storage, user_id
    ))
    return TaskResponse(task_id=str(task.id))


@app.post("/api/tasks/generate-resume-generic", response_model=TaskResponse)
async def generate_generic_resume_task(
    request: GenerateGenericResumeRequest, user_id: str = CurrentUser
) -> TaskResponse:
    """Generate a general-purpose resume without a JD.

    Synthesizes a generic target from the user's profile (summary + skills),
    upserts it as a 'General' JDRecord, then runs the normal pipeline.
    """
    from loom.services.generic_jd import upsert_generic_jd

    storage = get_storage()
    try:
        jd = await upsert_generic_jd(storage, user_id, request.focus, request.language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info("user_action", "resume.generate_generic",
            f"Generating generic resume ({jd.title})",
            jd_record_id=str(jd.id), language=request.language)
    except Exception:
        pass

    task = Task(
        type="generate_resume",
        status="pending",
        input_data={
            "jd_record_id": str(jd.id),
            "language": request.language,
            "format": request.format,
            "generic": True,
        },
        user_id=user_id,
    )
    await storage.save_task(task)
    asyncio.create_task(_run_generate_resume(
        task.id, str(jd.id), request.language, request.format, storage, user_id
    ))
    return TaskResponse(task_id=str(task.id))


class ReviewIssue(BaseModel):
    """One fact-check finding and how it was resolved."""
    type: str            # fabricated_metric / fabricated_tech / inflation / seniority / mislabel / other
    original: str        # the offending text as drafted
    resolution: str      # how it was fixed (rewritten to X / bullet removed)
    profile_basis: str | None = None   # what the profile actually supports


class ResumeReview(BaseModel):
    """Record of the fact-check that preceded this render.

    Required: an unreviewed resume must not be renderable. This is the
    flow-level counterpart to the pipeline's Phase 3b scrutiny step.
    """
    method: str = Field(..., pattern="^(subagent|self_review)$")
    issues_found: int = Field(..., ge=0)
    issues: list[ReviewIssue] = Field(default_factory=list)
    job: str | None = None    # "Title @ Company", for the log line


class TargetingIssue(BaseModel):
    """One targeting finding and how it was resolved."""
    type: str            # keyword_gap / irrelevant_content / no_positioning / burial / other
    problem: str
    resolution: str


class TargetingReview(BaseModel):
    """Record of the JD-targeting check.

    The fact gate caught 100% of fabrications because it was adversarial,
    fresh-context, and enforced. Targeting had no gate at all and produced
    37 findings across 8 resumes — the commonest being JD-named skills the
    profile genuinely supports being dropped from the resume entirely.
    This is the symmetric gate.
    """
    method: str = Field(..., pattern="^(subagent|self_review)$")
    # JD-named terms the profile supports AND the resume surfaces
    jd_terms_covered: list[str] = Field(default_factory=list)
    # JD-named terms the profile supports but the resume omits — every entry
    # here is a self-inflicted screening loss, so this should be empty
    jd_terms_dropped: list[str] = Field(default_factory=list)
    issues_found: int = Field(..., ge=0)
    issues: list[TargetingIssue] = Field(default_factory=list)


class RenderResumeRequest(BaseModel):
    """A caller-authored resume, ready to render.

    `context` mirrors what the internal pipeline builds:
      candidate{name,email,phone,location,github,linkedin}, summary,
      skills[{category,content}], experiences[{title,company,location,
      period,bullets[]}], projects[{name,bullets[]}],
      education[{degree,institution,period}], certifications[{name,year}]
    """
    context: dict[str, Any]
    review: ResumeReview
    targeting: TargetingReview
    language: str = Field(default="en", pattern="^(en|zh)$")
    jd_record_id: str | None = None
    notion_page_id: str | None = None
    compile_pdf: bool = True


@app.post("/api/resumes/render")
async def render_resume_endpoint(request: RenderResumeRequest):
    """Render + store a resume the caller already authored.

    No Claude calls happen here — this is templates and LaTeX only. Use it
    when an agent has done the reasoning and just needs the artifact.
    Pass notion_page_id to also write the PDF link back to the job tracker.
    """
    from loom.services.resume_render import render_and_store

    if not request.context.get("experiences") and not request.context.get("projects"):
        raise HTTPException(
            status_code=400,
            detail="context must include at least one of: experiences, projects",
        )
    for label, found, listed in (
        ("review", request.review.issues_found, len(request.review.issues)),
        ("targeting", request.targeting.issues_found, len(request.targeting.issues)),
    ):
        if found != listed:
            raise HTTPException(
                status_code=400,
                detail=(f"{label}.issues_found={found} but {listed} issues were "
                        f"listed — they must match"),
            )
    if request.targeting.jd_terms_dropped:
        # Every dropped term is a screening loss the caller could have avoided;
        # surface it rather than letting it pass silently.
        raise HTTPException(
            status_code=400,
            detail=("targeting.jd_terms_dropped is non-empty: "
                    f"{request.targeting.jd_terms_dropped[:8]} — the profile supports "
                    "these JD-named terms but the resume omits them. Surface them in "
                    "the resume (using the JD's own wording) and resubmit, or move any "
                    "term the profile does NOT actually support out of this list."),
        )
    try:
        result = await render_and_store(
            get_storage(), request.context, request.language,
            request.jd_record_id, request.compile_pdf,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("resume render failed")
        raise HTTPException(status_code=500, detail=f"Render failed: {e}")

    # Persist the fact-check into Loom's log table so the audit trail
    # survives the chat session that produced it.
    try:
        from loom.services.logger import logger as loom_logger
        rv = request.review
        by_type: dict[str, int] = {}
        for issue in rv.issues:
            by_type[issue.type] = by_type.get(issue.type, 0) + 1
        summary = ", ".join(f"{k}×{v}" for k, v in by_type.items()) or "no issues"
        await loom_logger.info(
            "workflow", "resume.review",
            f"Fact-check ({rv.method}) for {rv.job or 'resume'}: "
            f"{rv.issues_found} issue(s) — {summary}",
            resume_artifact_id=result["resume_artifact_id"],
            job=rv.job,
            method=rv.method,
            issues_found=rv.issues_found,
            issues_by_type=by_type,
            issues=[i.model_dump() for i in rv.issues],
            notion_page_id=request.notion_page_id,
        )

        tg = request.targeting
        tg_types: dict[str, int] = {}
        for issue in tg.issues:
            tg_types[issue.type] = tg_types.get(issue.type, 0) + 1
        await loom_logger.info(
            "workflow", "resume.targeting",
            f"Targeting check ({tg.method}) for {rv.job or 'resume'}: "
            f"{tg.issues_found} issue(s), {len(tg.jd_terms_covered)} JD term(s) covered",
            resume_artifact_id=result["resume_artifact_id"],
            job=rv.job,
            method=tg.method,
            issues_found=tg.issues_found,
            issues_by_type=tg_types,
            issues=[i.model_dump() for i in tg.issues],
            jd_terms_covered=tg.jd_terms_covered,
        )
    except Exception:
        logger.warning("review logging failed", exc_info=True)

    if request.notion_page_id and result.get("pdf_url"):
        try:
            import httpx as _httpx
            from loom.services.job_watcher import _headers, _write_back_success
            async with _httpx.AsyncClient(headers=_headers(), timeout=30.0) as c:
                await _write_back_success(c, request.notion_page_id, result["pdf_url"])
            result["notion_updated"] = True
        except Exception as e:
            logger.warning("Notion write-back failed: %s", e)
            result["notion_error"] = str(e)[:200]

    return {"status": "ok", **result}


class AddJobRequest(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    salary: str | None = None
    url: str | None = None
    jd_source: str | None = None
    match_score: float | None = None
    match_reason: str | None = None
    risk: str | None = None
    note: str | None = None
    generate_now: bool = False


@app.post("/api/jobs/tracker")
async def add_job_to_tracker(request: AddJobRequest, owner: str = OwnerOnly):
    """Add a job to the Notion tracker with 状态=待生成.

    Deduplicates on 链接: an existing row for the same URL is returned
    untouched. Set generate_now to kick off resume generation immediately
    instead of waiting for the daily 10:00 run.
    """
    from loom.services.job_watcher import (
        _enabled as jw_enabled,
        create_tracker_row,
        process_job_tracker,
    )

    if not jw_enabled():
        raise HTTPException(status_code=400,
                            detail="Job tracker not configured: set NOTION_TOKEN and NOTION_JOBS_DB_ID")
    try:
        result = await create_tracker_row(request.model_dump(exclude={"generate_now"}))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Notion write failed: {e}")

    if request.generate_now and not result.get("duplicate"):
        asyncio.create_task(process_job_tracker(get_storage(), limit=1))
        result["generation"] = "started"
    return {"status": "ok", **result}


@app.get("/api/jobs/tracker/pending")
async def list_pending_jobs(owner: str = OwnerOnly):
    """Jobs awaiting a resume (状态=待看, no resume link yet).

    Read-only view of the tracker queue, for agents that generate the
    resume themselves rather than invoking the server-side pipeline.
    """
    import httpx as _httpx

    from loom.services.job_watcher import (
        _enabled as jw_enabled,
        _headers,
        _query_pending,
    )

    if not jw_enabled():
        raise HTTPException(status_code=400,
                            detail="Job tracker not configured: set NOTION_TOKEN and NOTION_JOBS_DB_ID")
    try:
        async with _httpx.AsyncClient(headers=_headers(), timeout=30.0) as client:
            rows = await _query_pending(client)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Notion query failed: {e}")
    return {"count": len(rows), "jobs": rows}


@app.post("/api/tasks/process-job-tracker")
async def process_job_tracker_now(
    limit: int | None = None, background: bool = True, owner: str = OwnerOnly
):
    """Manually trigger the Notion job-tracker resume run.

    Runs server-side in the background by default (a full run can take
    tens of minutes — far beyond HTTP timeouts). Progress is visible in
    the Notion tracker itself; failures land in 简历备注.
    """
    from loom.services.job_watcher import (
        MAX_JOBS_PER_RUN,
        _enabled as jw_enabled,
        _run_lock,
        process_job_tracker,
    )

    if not jw_enabled():
        raise HTTPException(status_code=400,
                            detail="Job watcher not configured: set NOTION_TOKEN and NOTION_JOBS_DB_ID")
    limit = MAX_JOBS_PER_RUN if limit is None else limit
    if _run_lock.locked():
        return {"status": "busy", "detail": "a run is already in progress"}
    if background:
        asyncio.create_task(process_job_tracker(get_storage(), limit=limit))
        return {"status": "started", "limit": limit,
                "detail": "running in background; watch the Notion tracker for progress"}
    return await process_job_tracker(get_storage(), limit=limit)


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: UUID, user_id: str = CurrentUser):
    storage = get_storage()
    task = await storage.get_task(task_id, user_id=user_id)
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
async def download_resume_pdf(
    resume_id: UUID,
    user_id: str = CurrentUser,
    sig: str | None = None,
    request: Request = None,
):
    import hmac as _hmac
    import os

    # This route is exempt from AuthMiddleware: require either a valid
    # per-artifact signature (Notion links) or the Bearer key.
    from loom.services.signing import resume_pdf_sig
    auth = (request.headers.get("authorization", "") if request else "")
    bearer_ok = auth.startswith("Bearer ") and auth[7:] == LOOM_API_KEY
    sig_ok = bool(sig) and _hmac.compare_digest(sig, resume_pdf_sig(str(resume_id)))
    if not (bearer_ok or sig_ok):
        raise HTTPException(status_code=401, detail="Authentication required")

    # A signed link stands on its own — the signature already authorises this
    # one artifact, and the Notion reader has no session to scope it by.
    owner = None if sig_ok else user_id

    storage = get_storage()
    artifact = await storage.get_resume_artifact(resume_id, user_id=owner)
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
        await storage.update_resume_artifact(
            resume_id, {"pdf_path": pdf_path}, user_id=owner
        )

    # Build ASCII-safe filename
    parts = [artifact.created_at.strftime("%Y%m%d")]
    if artifact.jd_record_id:
        jd = await storage.get_jd_record(artifact.jd_record_id, user_id=owner)
        if jd:
            if jd.company:
                parts.append(jd.company.replace(" ", ""))
            parts.append(jd.title.replace(" ", "-"))
    filename = "-".join(parts) + ".pdf"
    # Strip non-ASCII characters for HTTP header safety
    filename = filename.encode("ascii", "ignore").decode("ascii")

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
    service: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: str = CurrentUser,
):
    storage = get_storage()
    entries, total = await storage.query_logs(
        category=category, level=level, search=search, service=service, limit=limit,
        offset=offset, user_id=user_id,
    )
    return {"total": total, "entries": entries}


@app.delete("/api/logs/clear")
async def clear_logs(older_than_days: int = 0, user_id: str = CurrentUser):
    storage = get_storage()
    deleted = await storage.delete_logs(older_than_days, user_id=user_id)
    return {"deleted": deleted}


@app.get("/api/logs/stats")
async def log_stats(user_id: str = CurrentUser):
    storage = get_storage()
    return await storage.get_log_stats(user_id=user_id)


# ══════════════════════════════════════════════════════════════
# Company scout
# ══════════════════════════════════════════════════════════════


class ScoutRequest(BaseModel):
    query: str
    near: str | None = None
    radius_m: int = 5000
    limit: int = 20
    enrich: bool = True
    # Open each site in a headless phone browser. Slower, but it is the
    # only way to see the defect this whole pitch rests on.
    render: bool = True


@app.post("/api/scout/search")
async def scout_search(request: ScoutRequest) -> dict:
    """Discover companies, then read their own sites for durable detail.

    The response carries Google-sourced fields for display only — see
    loom/services/company_scout.py for what may be persisted.
    """
    from loom.services.company_scout import scout, summarise
    from loom.services.google.client import GoogleAPIError

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    try:
        candidates = await scout(
            request.query,
            near=request.near,
            radius_m=request.radius_m,
            max_results=min(request.limit, 60),
            enrich=request.enrich,
            render=request.render,
        )
    except GoogleAPIError as e:
        # Usually: Places API not enabled, or the key's API restrictions
        # exclude it. Surface Google's own wording — it names the fix.
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {
        "stats": summarise(candidates),
        "candidates": [c.model_dump(mode="json") for c in candidates],
    }


class SurveyRequest(BaseModel):
    query: str = "cafe"
    areas: list[str] | None = None
    limit: int = 20


@app.get("/api/scout/areas")
async def scout_areas() -> dict:
    """The curated target list, with the reason to be in each place."""
    from loom.services.area_survey import areas_config, suggested_areas

    config = areas_config()
    return {
        "areas": suggested_areas(),
        "avoid": config.get("avoid", {}),
        "default": config.get("default_survey", []),
    }


@app.post("/api/scout/survey")
async def scout_survey(request: SurveyRequest) -> dict:
    """Scan several areas and rank them by how many workable leads they hold.

    Choosing where to prospect decides more than anything done afterwards, and
    it is the one question the tooling can answer with evidence rather than a
    hunch.
    """
    from loom.services.area_survey import survey

    results = await survey(
        request.query, request.areas, limit=max(5, min(request.limit, 30))
    )
    return {
        "query": request.query,
        "areas": [
            {**r.model_dump(mode="json"), "hit_rate": r.hit_rate} for r in results
        ],
    }


class SaveLeadsRequest(BaseModel):
    candidates: list[dict]


class UpdateLeadRequest(BaseModel):
    status: str | None = None
    notes: str | None = None
    # Typed in by hand when the crawler found none — plenty of shops only
    # publish an address on Instagram, which we don't scrape.
    emails: list[str] | None = None
    # Sharing is per lead and off by default — see migration 023.
    demo_public: bool | None = None


@app.post("/api/scout/leads")
async def save_scout_leads(
    request: SaveLeadsRequest, user_id: str = CurrentUser
) -> dict:
    """Save leads. Re-saving refreshes the audit but keeps status and notes."""
    storage = get_storage()
    result = await storage.upsert_scout_leads(request.candidates, user_id=user_id)
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info(
            "user_action", "scout.save_leads",
            f"Saved {result['created']} new, {result['updated']} updated leads",
            service="company_scout", **result,
        )
    except Exception:
        pass
    return result


@app.get("/api/scout/leads")
async def list_scout_leads(
    status: str | None = None, limit: int = 200, user_id: str = CurrentUser
) -> dict:
    storage = get_storage()
    leads = await storage.list_scout_leads(status=status, limit=limit, user_id=user_id)
    return {"total": len(leads), "leads": leads}


@app.patch("/api/scout/leads/{lead_id}")
async def update_scout_lead(
    lead_id: str, request: UpdateLeadRequest, user_id: str = CurrentUser
) -> dict:
    storage = get_storage()
    data = request.model_dump(exclude_none=True)
    if not await storage.update_scout_lead(lead_id, data, user_id=user_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "ok"}


@app.delete("/api/scout/leads/{lead_id}")
async def delete_scout_lead(lead_id: str, user_id: str = CurrentUser) -> dict:
    storage = get_storage()
    lead = await storage.get_scout_lead(lead_id, user_id=user_id)
    if lead and lead.get("demo_slug"):
        from loom.services.demo_builder import remove_demo
        remove_demo(lead["demo_slug"])
    if not await storage.delete_scout_lead(lead_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "ok"}


async def _require_lead(lead_id: str, user_id: str) -> tuple[Any, dict]:
    """The lead, or 404 — someone else's lead is indistinguishable from absent."""
    storage = get_storage()
    lead = await storage.get_scout_lead(lead_id, user_id=user_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return storage, lead


@app.post("/api/scout/leads/{lead_id}/harvest")
async def harvest_scout_lead(lead_id: str, user_id: str = CurrentUser) -> dict:
    """Read the business's own pages for menu, hours, images and socials."""
    from loom.services.site_harvest import harvest_lead

    storage, lead = await _require_lead(lead_id, user_id)
    harvest = await harvest_lead(lead)
    await storage.update_scout_lead(
        lead_id,
        {"harvest": harvest.model_dump(mode="json"), "harvested_at": datetime.utcnow()},
        user_id=user_id,
    )
    return {"harvest": harvest.model_dump(mode="json"), "usable": harvest.is_usable}


@app.post("/api/scout/leads/{lead_id}/plan")
async def plan_scout_demo(lead_id: str, user_id: str = CurrentUser) -> dict:
    """Read the evidence and propose art directions. Generates nothing.

    One cheap call whose output goes back to the panel to be adjusted — the
    expensive step then runs only on directions that were actually chosen.
    """
    from loom.services.demo_planner import plan_demo
    from loom.services.site_harvest import Harvest

    storage, lead = await _require_lead(lead_id, user_id)
    if not lead.get("harvest"):
        raise HTTPException(status_code=400, detail="Harvest the site first")

    lead = {**lead, "primary_type": (lead.get("google_extra") or {}).get("primary_type")}
    plan = await plan_demo(lead, Harvest(**lead["harvest"]))
    if plan.error:
        raise HTTPException(status_code=502, detail=plan.error)

    await storage.update_scout_lead(
        lead_id,
        {"demo_plan": plan.model_dump(mode="json"), "planned_at": datetime.utcnow()},
        user_id=user_id,
    )
    return plan.model_dump(mode="json")


@app.post("/api/scout/leads/{lead_id}/demo")
async def build_scout_demo(
    lead_id: str, directions: str = "", count: int = 3, user_id: str = CurrentUser
) -> dict:
    """Generate several designs of the mock site, one per art direction.

    Nothing is published here — the variants are stored so they can be
    compared as thumbnails, and the chosen one becomes the live page.
    """
    import base64

    from loom.services.demo_agent import build_variants
    from loom.services.demo_builder import slug_for, write_demo
    from loom.services.site_harvest import Harvest

    storage, lead = await _require_lead(lead_id, user_id)
    if not lead.get("harvest"):
        raise HTTPException(status_code=400, detail="Harvest the site first")

    harvest = Harvest(**lead["harvest"])
    # primary_type is cached Places content, so it rides in google_extra
    # and expires with the rest of it. The art direction is picked from it.
    lead = {**lead, "primary_type": (lead.get("google_extra") or {}).get("primary_type")}

    # Explicit directions come from the reviewed plan; the count fallback
    # only exists for a lead that was never planned.
    wanted = [d.strip() for d in directions.split(",") if d.strip()]
    if not wanted and lead.get("demo_plan"):
        wanted = [p["direction"] for p in (lead["demo_plan"].get("picks") or [])]
    results = await build_variants(
        lead, harvest, directions=wanted or None, count=max(1, min(count, 6))
    )
    usable = {d: r for d, r in results.items() if r.html}
    if not usable:
        detail = "; ".join(
            f"{d}: {[v.code for v in r.remaining]}" for d, r in results.items()
        )
        raise HTTPException(status_code=502, detail=f"No variant built — {detail}")

    variants = {
        direction: {
            "html": r.html,
            "thumb": base64.b64encode(r.thumb).decode() if r.thumb else None,
            "rounds": r.rounds,
            "engine": r.engine,
            "remaining": [v.model_dump() for v in r.remaining],
            "built_at": datetime.utcnow().isoformat(),
        }
        for direction, r in usable.items()
    }
    # The first is only a default; the point of the set is that it gets changed.
    active = lead.get("demo_active") if lead.get("demo_active") in variants else next(iter(variants))
    slug = lead.get("demo_slug") or slug_for(
        lead.get("google_name") or lead.get("site_title") or "",
        lead["place_id"],
        user_id,
    )
    write_demo(slug, variants[active]["html"])
    await storage.update_scout_lead(
        lead_id,
        {
            "demo_slug": slug,
            "demo_variants": variants,
            "demo_active": active,
            "demo_html": variants[active]["html"],
            "demo_built_at": datetime.utcnow(),
        },
        user_id=user_id,
    )
    try:
        from loom.services.logger import logger as loom_logger
        await loom_logger.info(
            "user_action", "scout.demo_built",
            f"Built {len(variants)} variants for {lead.get('google_name')}",
            service="company_scout", variants=list(variants),
            active=active,
            failed=[d for d in results if d not in usable],
        )
    except Exception:
        pass

    return {
        "slug": slug,
        "active": active,
        "variants": [
            {
                "direction": d,
                "rounds": v["rounds"],
                "remaining": v["remaining"],
                "bytes": len(v["html"]),
                "has_thumb": bool(v["thumb"]),
            }
            for d, v in variants.items()
        ],
        "failed": [d for d in results if d not in usable],
    }


@app.post("/api/scout/leads/{lead_id}/demo/{direction}/select")
async def select_scout_demo(
    lead_id: str, direction: str, user_id: str = CurrentUser
) -> dict:
    """Make one variant the published page."""
    from loom.services.demo_builder import write_demo

    storage, lead = await _require_lead(lead_id, user_id)
    variants = lead.get("demo_variants") or {}
    if direction not in variants:
        raise HTTPException(status_code=404, detail="No such variant")
    html = variants[direction]["html"]
    if lead.get("demo_slug"):
        write_demo(lead["demo_slug"], html)
    await storage.update_scout_lead(
        lead_id, {"demo_active": direction, "demo_html": html},
        user_id=user_id,
    )
    return {"active": direction}


@app.get("/api/scout/leads/{lead_id}/demo/{direction}/thumb")
async def scout_demo_thumb(
    lead_id: str, direction: str, user_id: str = CurrentUser
) -> Response:
    """Phone-shaped JPEG of one variant, for comparing designs at a glance."""
    import base64

    _, lead = await _require_lead(lead_id, user_id)
    variant = (lead.get("demo_variants") or {}).get(direction) or {}
    if not variant.get("thumb"):
        raise HTTPException(status_code=404, detail="No thumbnail")
    return Response(
        content=base64.b64decode(variant["thumb"]),
        media_type="image/jpeg",
        # Rebuilding designs replaces every thumbnail, so a cached one
        # would show the previous set and read as a failed rebuild.
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/api/scout/leads/{lead_id}/demo")
async def preview_scout_demo(lead_id: str, user_id: str = CurrentUser) -> Response:
    """Serve the generated demo so it can be previewed before publishing."""
    from loom.services.demo_builder import DEMO_ROOT

    _, lead = await _require_lead(lead_id, user_id)
    slug = lead.get("demo_slug")
    path = DEMO_ROOT / slug / "index.html" if slug else None
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="No demo built yet")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/html",
        # Never cache: this is a preview of something being iterated on, and
        # a browser holding yesterday's copy looks exactly like "selecting a
        # design did nothing".
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/api/scout/templates")
async def scout_templates() -> dict:
    """The email formats available, for a picker."""
    from loom.services.email_templates import available

    return {"templates": available()}


class DraftRequest(BaseModel):
    template: str | None = None
    # Anything the lead can't supply: a name once they reply, an agreed price,
    # the live URL at handover.
    extra: dict[str, str] = {}


@app.post("/api/scout/leads/{lead_id}/draft")
async def draft_scout_outreach(
    lead_id: str, request: DraftRequest, user_id: str = CurrentUser
) -> dict:
    """Fill an email format from the lead. Drafting only — nothing is sent.

    No model call: the audit findings are already written for the owner to
    read, so the sentence that makes the pitch is a slot, not a generation.
    """
    from loom.services.email_templates import (
        MissingSlotsError,
        ProblemTooWeakError,
        render,
        suggest_template,
    )

    storage, lead = await _require_lead(lead_id, user_id)
    key = request.template or suggest_template(lead)

    try:
        draft = render(
            key,
            lead,
            public_base=os.environ.get("LOOM_PUBLIC_URL", ""),
            **request.extra,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ProblemTooWeakError as e:
        # Not a failure to fix — a lead not worth writing to.
        raise HTTPException(status_code=409, detail=str(e)) from e
    except MissingSlotsError as e:
        # Naming the gaps is the useful failure: they are what the panel has
        # to ask for before this email can exist.
        raise HTTPException(
            status_code=400,
            detail={"error": str(e), "missing": e.slots, "template": key},
        ) from e

    await storage.update_scout_lead(
        lead_id,
        {
            "draft_subject": draft["subject"],
            "draft_body": draft["body"],
            "drafted_at": datetime.utcnow(),
        },
        user_id=user_id,
    )
    # Put it in the Notion table so approval happens away from this machine.
    try:
        from loom.services.notion_outreach import push_draft

        base = os.environ.get("LOOM_PUBLIC_URL", "").rstrip("/")
        slug = lead.get("demo_slug")
        page_id = await push_draft(
            lead, draft,
            demo_url=f"{base}/demo/{slug}" if slug and base and lead.get("demo_public") else "",
        )
        draft["notion_page_id"] = page_id
    except Exception as e:
        # A drafting call must not fail because Notion is down.
        draft["notion_error"] = str(e)[:200]

    return draft


@app.post("/api/scout/outreach/send-approved")
async def send_approved_outreach(
    dry_run: bool | None = None, owner: str = OwnerOnly
) -> dict:
    """Send the emails a human marked Approved in Notion.

    Nothing here chooses recipients: it acts only on rows already approved,
    and writes the outcome back before moving on so a crash cannot send twice.
    """
    from loom.services.mailer import send_approved

    return await send_approved(dry_run=dry_run)


@app.post("/api/scout/outreach/poll-replies")
async def poll_outreach_replies(days: int = 30, owner: str = OwnerOnly) -> dict:
    """Pull replies into the outreach table, and honour any opt-out.

    Read-only against the mailbox — nothing is sent, deleted, or even marked
    read. What it changes is the Notion row and, for an opt-out, the lead's
    status, which is what stops the next email being drafted.

    Worth running on a schedule rather than by hand: the outreach signature
    undertakes to remove someone within five business days of their asking,
    and a poll nobody remembers to run is not a mechanism.
    """
    from loom.services.replies import poll

    return await poll(days=days)


@app.get("/api/scout/outreach/queue")
async def outreach_queue(owner: str = OwnerOnly) -> dict:
    """What is currently waiting for approval to be acted on."""
    from loom.services import notion_outreach
    from loom.services.mailer import configured

    rows = await notion_outreach.approved_rows()
    return {
        "smtp_configured": configured(),
        "notion_enabled": notion_outreach.enabled(),
        "approved": [
            {"business": r["business"], "to": r["to"], "subject": r["subject"]}
            for r in rows
        ],
    }


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("LOOM_API_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
