"""Backfill star_data and tech_stack for existing bullets using Claude Haiku."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from loom.llm import Claude, Model
from loom.storage.repository import BulletRepository, DataStorage, ProfileRepository

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """Extract structured information from this resume bullet.

Bullet: {content_en}
{raw_text_line}
Context: This is from {company} - {title}

Return ONLY valid JSON, no markdown:
{{
  "star_data": {{
    "situation": "background and challenge context",
    "task": "what the candidate was responsible for",
    "action": "specific actions taken",
    "result_quantified": "measurable outcomes with numbers",
    "result_qualitative": "non-quantified but meaningful outcomes"
  }},
  "tech_stack": [
    {{
      "name": "technology name",
      "role": "what problem it solved here",
      "ecosystem_group": "e.g. backend/frontend/data_pipeline/cloud"
    }}
  ],
  "type": "business_impact|technical_design|implementation|scale|collaboration|problem_solving",
  "confidence": "high|medium|low"
}}

Rules:
- Only extract what's explicitly stated or strongly implied
- If no quantified result exists, leave result_quantified as ""
- Only include technologies actually mentioned in the bullet
- confidence=low if bullet is vague or missing key STAR elements
- For type, pick the BEST match from the options"""


def _needs_backfill(bullet: Any) -> bool:
    """Check if a bullet needs star_data or tech_stack backfill."""
    star = bullet.star_data
    tech = bullet.tech_stack
    star_empty = not star or star == {} or all(v == "" for v in star.values())
    tech_empty = not tech or tech == []
    return star_empty or tech_empty


async def backfill_bullets(
    storage: DataStorage,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict:
    """Backfill star_data and tech_stack for bullets missing them.

    Returns summary dict with counts.
    """
    claude = Claude()
    bullet_repo = BulletRepository(storage)
    profile_repo = ProfileRepository(storage)

    # Get all experiences with bullets
    exp_bullets = await bullet_repo.get_all_bullets_for_user("local")

    # Collect bullets needing backfill
    to_process: list[tuple[Any, Any]] = []  # (experience, bullet)
    skipped = 0

    for exp, bullets in exp_bullets:
        for b in bullets:
            if _needs_backfill(b):
                to_process.append((exp, b))
            else:
                skipped += 1

    total = len(to_process)
    if limit:
        to_process = to_process[:limit]

    print(f"Total bullets needing backfill: {total}")
    print(f"Already have data (skipped): {skipped}")
    if limit:
        print(f"Processing first {len(to_process)} (--limit {limit})")
    print()

    if dry_run:
        print("=== DRY RUN — no changes will be made ===\n")
        for i, (exp, b) in enumerate(to_process):
            content = (b.content_en or b.raw_text or "")[:80]
            star_keys = list(b.star_data.keys()) if b.star_data else []
            tech_count = len(b.tech_stack) if b.tech_stack else 0
            print(f"  [{i+1}/{len(to_process)}] {exp.company_en} | {exp.title_en}")
            print(f"    {content}...")
            print(f"    star_data keys: {star_keys}, tech_stack items: {tech_count}")
            print()
        return {"total": total, "would_process": len(to_process), "skipped": skipped}

    # Process each bullet
    updated = 0
    failed = 0
    failures: list[dict] = []

    for i, (exp, b) in enumerate(to_process):
        content = b.content_en or b.raw_text or ""
        short = content[:60]
        print(f"  [{i+1}/{len(to_process)}] {short}...")

        raw_text_line = f"Raw text: {b.raw_text}" if b.raw_text and b.raw_text != content else ""

        prompt = EXTRACT_PROMPT.format(
            content_en=content,
            raw_text_line=raw_text_line,
            company=exp.company_en,
            title=exp.title_en,
        )

        try:
            result = await claude.extract_json(
                prompt=prompt,
                model=Model.HAIKU,
            )

            star_data = result.get("star_data", {})
            tech_stack = result.get("tech_stack", [])
            extracted_type = result.get("type")
            confidence = result.get("confidence", "medium")

            # Build update dict
            update: dict[str, Any] = {}

            if star_data and any(v for v in star_data.values()):
                update["star_data"] = star_data

            if tech_stack:
                update["tech_stack"] = tech_stack

            if confidence:
                update["confidence"] = confidence

            # Only update type if current is default "implementation"
            if extracted_type and b.type.value == "implementation" and extracted_type != "implementation":
                update["type"] = extracted_type

            if update:
                await storage.update_bullet(b.id, update)
                updated += 1

                s_len = len(star_data.get("situation", ""))
                t_len = len(star_data.get("task", ""))
                a_len = len(star_data.get("action", ""))
                r_len = len(star_data.get("result_quantified", ""))
                tech_count = len(tech_stack)
                print(f"    OK: S={s_len} T={t_len} A={a_len} R={r_len} tech={tech_count} items")
            else:
                print(f"    SKIP: extraction returned empty")
                skipped += 1

        except Exception as e:
            failed += 1
            print(f"    FAIL: {e}")
            failures.append({
                "bullet_id": str(b.id),
                "content_en": content[:200],
                "error": str(e),
            })

    # Write failures
    if failures:
        fail_path = Path(__file__).parent / "backfill_failures.json"
        fail_path.write_text(json.dumps(failures, indent=2, ensure_ascii=False))
        print(f"\nFailures written to {fail_path}")

    print(f"\n=== Summary ===")
    print(f"  Total needing backfill: {total}")
    print(f"  Updated: {updated}")
    print(f"  Skipped (had data): {skipped}")
    print(f"  Failed: {failed}")

    return {"total": total, "updated": updated, "skipped": skipped, "failed": failed}
