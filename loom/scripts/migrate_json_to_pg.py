"""Migrate all data from JsonFileDataStorage to PostgreSQL."""

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()


async def migrate():
    from loom.storage.json_file import JsonFileDataStorage
    from loom.storage.postgres import PostgresDataStorageContext

    # Load from JSON
    json_store = JsonFileDataStorage()

    profile = await json_store.get_profile("local")
    if not profile:
        print("No profile found in JSON storage")
        return

    print(f"=== Migrating from {json_store._path} ===")
    print()

    async with PostgresDataStorageContext() as pg:
        # 1. Profile
        existing = await pg.get_profile("local")
        if existing:
            print("Profile already exists in PG, updating...")
            await pg.update_profile(existing.id, {
                "name_en": profile.name_en,
                "name_zh": profile.name_zh,
                "email": profile.email,
                "phone": profile.phone,
                "location_en": profile.location_en,
                "location_zh": profile.location_zh,
                "summary_en": profile.summary_en,
                "summary_zh": profile.summary_zh,
            })
            pg_profile = existing
        else:
            await pg.save_profile(profile)
            pg_profile = profile
        print(f"Profile: {pg_profile.name_en}")

        # 2. Skills
        skills = await json_store.get_skills(profile.id)
        existing_skills = await pg.get_skills(pg_profile.id)
        existing_skill_names = {s.name for s in existing_skills}
        new_skills = 0
        for s in skills:
            if s.name not in existing_skill_names:
                s.profile_id = pg_profile.id
                await pg.save_skill(s)
                new_skills += 1
        print(f"Skills: {len(skills)} total, {new_skills} new")

        # 3. Experiences + Bullets
        experiences = await json_store.get_experiences(profile.id)
        existing_exps = await pg.get_experiences(pg_profile.id)
        existing_exp_ids = {e.id for e in existing_exps}
        new_exps = 0
        total_bullets = 0
        new_bullets = 0

        for exp in experiences:
            if exp.id not in existing_exp_ids:
                exp.profile_id = pg_profile.id
                await pg.save_experience(exp)
                new_exps += 1

            # Bullets for this experience
            bullets = await json_store.get_bullets(exp.id)
            existing_bullets = await pg.get_bullets(exp.id)
            existing_bullet_ids = {b.id for b in existing_bullets}
            total_bullets += len(bullets)

            for b in bullets:
                if b.id not in existing_bullet_ids:
                    await pg.save_bullet(b)
                    new_bullets += 1

        print(f"Experiences: {len(experiences)} total, {new_exps} new")
        print(f"Bullets: {total_bullets} total, {new_bullets} new")

        # 4. Projects
        projects = await json_store.get_projects(profile.id)
        existing_projects = await pg.get_projects(pg_profile.id)
        existing_proj_ids = {p.id for p in existing_projects}
        new_projs = 0
        for p in projects:
            if p.id not in existing_proj_ids:
                p.profile_id = pg_profile.id
                await pg.save_project(p)
                new_projs += 1
        print(f"Projects: {len(projects)} total, {new_projs} new")

        # 5. Education
        education = await json_store.get_education(profile.id)
        existing_edu = await pg.get_education(pg_profile.id)
        existing_edu_ids = {e.id for e in existing_edu}
        new_edu = 0
        for e in education:
            if e.id not in existing_edu_ids:
                e.profile_id = pg_profile.id
                await pg.save_education(e)
                new_edu += 1
        print(f"Education: {len(education)} total, {new_edu} new")

        # 6. JD Records
        jd_records = await json_store.list_jd_records("local")
        new_jds = 0
        for jd in jd_records:
            existing_jd = await pg.get_jd_record(jd.id)
            if not existing_jd:
                await pg.save_jd_record(jd)
                new_jds += 1
        print(f"JD Records: {len(jd_records)} total, {new_jds} new")

        # 7. Resume Artifacts
        artifacts = await json_store.list_resume_artifacts("local")
        new_artifacts = 0
        for a in artifacts:
            existing_a = await pg.get_resume_artifact(a.id)
            if not existing_a:
                await pg.save_resume_artifact(a)
                new_artifacts += 1
        print(f"Resume Artifacts: {len(artifacts)} total, {new_artifacts} new")

    print()
    print("Migration complete!")

    # Backup JSON file
    src = json_store._path
    backup = src.with_suffix(".json.bak")
    shutil.copy2(src, backup)
    print(f"JSON backup: {backup}")


if __name__ == "__main__":
    asyncio.run(migrate())
