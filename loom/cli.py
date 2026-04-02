"""Loom CLI - command line interface for running workflows."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Loom - AI-native automation workflow engine."""
    pass


@main.command("run-resume")
@click.option("--jd", type=str, help="JD text directly")
@click.option("--jd-file", type=click.Path(exists=True), help="Path to JD file")
@click.option("--lang", type=click.Choice(["en", "zh"]), default="en", help="Output language")
@click.option("--output-dir", type=click.Path(), default="./output", help="Output directory")
@click.option("--seed", is_flag=True, help="Seed sample profile data for testing")
@click.option("--db", type=click.Choice(["memory", "postgres"]), default="memory",
              help="Storage backend (default: memory)")
def run_resume(jd: Optional[str], jd_file: Optional[str], lang: str, output_dir: str,
               seed: bool, db: str):
    """Run the resume-tailor workflow.

    Provide JD text directly with --jd or from a file with --jd-file.

    Use --db=postgres to use PostgreSQL storage (requires DATABASE_URL env var).
    """
    if not jd and not jd_file:
        click.echo("Error: Either --jd or --jd-file is required", err=True)
        sys.exit(1)

    if jd_file:
        jd_text = Path(jd_file).read_text()
    else:
        jd_text = jd

    click.echo("Starting resume-tailor workflow...")
    click.echo(f"  Language: {lang}")
    click.echo(f"  Storage: {db}")
    click.echo(f"  JD length: {len(jd_text)} chars")
    if seed:
        click.echo("  Seeding sample profile data...")
    click.echo()

    asyncio.run(_run_resume_workflow(jd_text, lang, output_dir, seed, db))


async def _run_resume_workflow(jd_text: str, lang: str, output_dir: str, seed: bool = False,
                               db: str = "memory"):
    """Execute the resume-tailor workflow."""
    # Import steps to register them
    import loom.steps  # noqa: F401

    # Initialize storage based on backend choice
    if db == "postgres":
        from loom.storage.postgres import PostgresDataStorageContext
        # For postgres, we use context manager pattern
        async with PostgresDataStorageContext() as storage:
            await _execute_workflow(storage, jd_text, lang, output_dir, seed)
        return
    else:
        # In-memory storage
        from loom.storage.init_db import init_db
        storage = await init_db()
        await _execute_workflow(storage, jd_text, lang, output_dir, seed)


async def _execute_workflow(storage, jd_text: str, lang: str, output_dir: str, seed: bool = False):
    """Execute the workflow with given storage."""
    from loom.core import WorkflowRunner, step_registry
    from loom.storage.init_db import get_workflow_definitions
    from loom.triggers import ManualTrigger

    # Seed sample data if requested
    if seed:
        from loom.storage.seed import seed_sample_profile
        await seed_sample_profile(storage)

    # Get workflow definition
    workflows = get_workflow_definitions()
    workflow_def = workflows.get("resume-tailor")
    if not workflow_def:
        click.echo("Error: resume-tailor workflow not found", err=True)
        return

    click.echo(f"Registered steps: {step_registry.list_steps()}")
    click.echo()

    # Create trigger and emit context
    trigger = ManualTrigger()
    trigger.set_data({
        "jd_raw_text": jd_text,
        "language": lang,
    })
    context = await trigger.emit()

    click.echo(f"WorkflowRun ID: {context.workflow_id}")
    click.echo()

    # Run workflow
    runner = WorkflowRunner(workflow_def, storage)

    start_time = datetime.now()
    step_times = {}

    try:
        # Track step execution times
        current_step = None
        step_start = None

        # Import step classes to create with storage
        from loom.steps import (
            GenerateResumeStep,
            MatchProfileStep,
            ParseJDStep,
            SelectBulletsStep,
        )

        # Map step names to classes with storage injection
        step_classes = {
            "parse-jd": ParseJDStep,
            "match-profile": MatchProfileStep,
            "select-bullets": SelectBulletsStep,
            "generate-resume": GenerateResumeStep,
        }

        for step_config in sorted(workflow_def.steps, key=lambda s: s.get("order", 0)):
            step_name = step_config["name"]
            current_step = step_name
            step_start = datetime.now()

            click.echo(f"  Running {step_name}...", nl=False)

            # Create step with shared storage (all steps get storage for usage tracking)
            step_class = step_classes.get(step_name)
            if step_class:
                step = step_class(storage=storage)
            else:
                step = step_registry.get(step_name)

            context = await step.run(context)

            elapsed = (datetime.now() - step_start).total_seconds()
            step_times[step_name] = elapsed
            click.echo(f" ✓ ({elapsed:.1f}s)")

        total_time = (datetime.now() - start_time).total_seconds()
        click.echo()
        click.echo(f"✓ Workflow completed in {total_time:.1f}s")

        # Save outputs
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        artifact_id = context.data.get("resume_artifact_id")
        if artifact_id:
            from uuid import UUID
            artifact = await storage.get_resume_artifact(UUID(artifact_id))

            if artifact and artifact.content_md:
                md_path = output_path / f"resume_{artifact_id[:8]}.md"
                md_path.write_text(artifact.content_md)
                click.echo(f"  Markdown: {md_path}")

            if artifact and artifact.content_tex:
                tex_path = output_path / f"resume_{artifact_id[:8]}.tex"
                tex_path.write_text(artifact.content_tex)
                click.echo(f"  LaTeX: {tex_path}")

        # Print summary
        click.echo()
        _print_run_summary(context, step_times)

        # Print usage summary
        await _print_usage_summary(storage)

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        click.echo(f" ✗ Failed")
        click.echo()
        click.echo(f"✗ Workflow failed after {elapsed:.1f}s", err=True)
        click.echo(f"  Step: {current_step}", err=True)
        click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


def _print_run_summary(context, step_times: dict):
    """Print a formatted summary of the workflow run."""
    click.echo("┌" + "─" * 50 + "┐")
    click.echo(f"│ {'Workflow Summary':^48} │")
    click.echo("├" + "─" * 50 + "┤")

    for step_name, elapsed in step_times.items():
        status = "✓"
        click.echo(f"│ {status} {step_name:<30} {elapsed:>10.1f}s │")

    click.echo("└" + "─" * 50 + "┘")

    # Print key results
    if "match_result" in context.data:
        match = context.data["match_result"]
        click.echo()
        click.echo(f"Match Score: {match.get('score', 'N/A')}/10")
        if match.get("hard_skill_gaps"):
            click.echo(f"Skill Gaps: {', '.join(match['hard_skill_gaps'])}")

    if "selected_bullets" in context.data:
        selected = context.data["selected_bullets"]
        click.echo(f"Bullets Selected: {selected.get('total_count', 0)}")


async def _print_usage_summary(storage):
    """Print token usage summary for this run."""
    from decimal import Decimal
    from loom.storage import UsageRepository

    repo = UsageRepository(storage)
    # Get recent usage (from this run)
    recent = await repo.get_recent_usage(limit=50)

    if not recent:
        return

    # Aggregate
    total_input = sum(u.input_tokens for u in recent)
    total_output = sum(u.output_tokens for u in recent)
    total_cost = sum(Decimal(u.total_cost_usd) for u in recent)

    click.echo()
    click.echo("┌" + "─" * 50 + "┐")
    click.echo(f"│ {'Token Usage (this run)':^48} │")
    click.echo("├" + "─" * 50 + "┤")
    click.echo(f"│ {'API Calls:':<25} {len(recent):>21} │")
    click.echo(f"│ {'Input Tokens:':<25} {total_input:>21,} │")
    click.echo(f"│ {'Output Tokens:':<25} {total_output:>21,} │")
    click.echo(f"│ {'Est. Cost (USD):':<25} {'$' + str(total_cost):>20} │")
    click.echo("└" + "─" * 50 + "┘")


@main.command("resume-status")
@click.option("--limit", type=int, default=5, help="Number of recent runs to show")
def resume_status(limit: int):
    """Show recent workflow execution status.

    Note: Currently shows in-memory runs only.
    Database persistence coming soon.
    """
    click.echo("Recent workflow runs:")
    click.echo()
    click.echo("(No persistent storage yet - runs are in-memory only)")
    click.echo("Use 'loom run-resume' to execute a new workflow.")


@main.command("resume-retry")
@click.option("--run-id", type=str, help="WorkflowRun ID to retry")
def resume_retry(run_id: Optional[str]):
    """Retry a failed workflow from checkpoint.

    If --run-id is not provided, retries the most recent failed run.

    Note: Currently requires persistent storage (coming soon).
    """
    if run_id:
        click.echo(f"Retrying workflow run: {run_id}")
    else:
        click.echo("Looking for most recent failed run...")

    click.echo()
    click.echo("(Checkpoint resume requires persistent storage - coming soon)")
    click.echo("For now, please run a new workflow with 'loom run-resume'.")


@main.command("list-steps")
def list_steps():
    """List all registered workflow steps."""
    # Import to register
    import loom.steps  # noqa: F401
    from loom.core import step_registry

    click.echo("Registered steps:")
    for step_name in step_registry.list_steps():
        click.echo(f"  - {step_name}")


@main.command("list-workflows")
def list_workflows():
    """List all available workflows."""
    from loom.storage.init_db import get_workflow_definitions

    workflows = get_workflow_definitions()
    click.echo("Available workflows:")
    for name, workflow in workflows.items():
        click.echo(f"  {name}")
        click.echo(f"    Trigger: {workflow.trigger_type.value}")
        steps = [s["name"] for s in sorted(workflow.steps, key=lambda x: x.get("order", 0))]
        click.echo(f"    Steps: {' → '.join(steps)}")


@main.command("db-init")
@click.option("--seed", is_flag=True, help="Seed sample profile data after init")
@click.option("--reset", is_flag=True, help="Drop all tables before creating (destructive)")
def db_init(seed: bool, reset: bool):
    """Initialize the database (create all tables).

    Creates all tables using SQLAlchemy models.
    Use --reset to drop and recreate all tables (for schema changes).
    Optionally seeds sample data for testing.

    Requires DATABASE_URL environment variable or uses default:
    postgresql+asyncpg://postgres:postgres@localhost:5432/loom
    """
    asyncio.run(_db_init(seed, reset))


async def _db_init(seed: bool, reset: bool = False):
    """Async database initialization."""
    from loom.storage.database import get_engine
    from loom.storage.models import Base

    click.echo("Initializing database...")

    engine = get_engine()

    async with engine.begin() as conn:
        if reset:
            click.echo("Dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    click.echo("✓ Database tables created")

    if seed:
        click.echo("Seeding sample data...")
        from loom.storage.postgres import PostgresDataStorageContext
        from loom.storage.seed import seed_sample_profile

        async with PostgresDataStorageContext() as storage:
            await seed_sample_profile(storage)
        click.echo("✓ Sample data seeded")

    click.echo()
    click.echo("Database initialized successfully!")
    click.echo("Run 'loom db-migrate' for production migrations.")


@main.command("db-migrate")
@click.option("--revision", type=str, default="head", help="Target revision (default: head)")
def db_migrate(revision: str):
    """Run database migrations using Alembic.

    Applies pending migrations to bring database schema up to date.

    Requires DATABASE_URL environment variable.
    """
    import subprocess

    click.echo(f"Running migrations to revision: {revision}")

    result = subprocess.run(
        ["alembic", "upgrade", revision],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo("✓ Migrations completed successfully")
        if result.stdout:
            click.echo(result.stdout)
    else:
        click.echo("✗ Migration failed", err=True)
        if result.stderr:
            click.echo(result.stderr, err=True)
        sys.exit(1)


@main.command("db-revision")
@click.option("-m", "--message", required=True, help="Revision message")
@click.option("--autogenerate", is_flag=True, help="Auto-generate migration from models")
def db_revision(message: str, autogenerate: bool):
    """Create a new database migration revision.

    Creates a new migration file in loom/storage/migrations/versions/.
    """
    import subprocess

    click.echo(f"Creating new revision: {message}")

    cmd = ["alembic", "revision", "-m", message]
    if autogenerate:
        cmd.append("--autogenerate")

    result = subprocess.run(
        cmd,
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo("✓ Revision created")
        if result.stdout:
            click.echo(result.stdout)
    else:
        click.echo("✗ Failed to create revision", err=True)
        if result.stderr:
            click.echo(result.stderr, err=True)
        sys.exit(1)


@main.command("serve")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=None, type=int, help="Port to bind to (default: LOOM_API_PORT or 8001)")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str, port: int | None, reload: bool):
    """Start the API server.

    Runs the FastAPI application with uvicorn.
    """
    import uvicorn

    if port is None:
        port = int(os.environ.get("LOOM_API_PORT", 8001))
    click.echo(f"Starting Loom API server...")
    click.echo(f"  Host: {host}")
    click.echo(f"  Port: {port}")
    click.echo(f"  Reload: {reload}")
    click.echo()
    click.echo(f"API docs: http://{host}:{port}/docs")
    click.echo()

    uvicorn.run(
        "loom.api:app",
        host=host,
        port=port,
        reload=reload,
    )


@main.command("usage")
@click.option("--days", type=int, default=30, help="Number of days to look back")
@click.option("--recent", type=int, default=0, help="Show N most recent API calls")
@click.option("--db", type=click.Choice(["memory", "postgres"]), default="memory",
              help="Storage backend (default: memory)")
def usage(days: int, recent: int, db: str):
    """Show token usage and cost statistics.

    Displays aggregated usage by model and step, with total costs.
    Use --recent N to show the N most recent individual API calls.
    """
    asyncio.run(_show_usage(days, recent, db))


async def _show_usage(days: int, recent: int, db: str):
    """Display usage statistics."""
    from loom.storage import UsageRepository

    # Initialize storage
    if db == "postgres":
        from loom.storage.postgres import PostgresDataStorageContext
        async with PostgresDataStorageContext() as storage:
            await _display_usage(storage, days, recent)
    else:
        from loom.storage import InMemoryDataStorage
        storage = InMemoryDataStorage()
        await _display_usage(storage, days, recent)


async def _display_usage(storage, days: int, recent: int):
    """Display usage with given storage."""
    from loom.storage import UsageRepository

    repo = UsageRepository(storage)
    summary = await repo.get_usage_summary(days=days)

    # Header
    click.echo()
    click.echo("┌" + "─" * 60 + "┐")
    click.echo(f"│ {'Token Usage Summary':^58} │")
    click.echo(f"│ {'Last ' + str(days) + ' days':^58} │")
    click.echo("├" + "─" * 60 + "┤")

    # Totals
    click.echo(f"│ {'Total API Calls:':<30} {summary.total_calls:>26} │")
    click.echo(f"│ {'Total Input Tokens:':<30} {summary.total_input_tokens:>26,} │")
    click.echo(f"│ {'Total Output Tokens:':<30} {summary.total_output_tokens:>26,} │")
    click.echo(f"│ {'Total Cost (USD):':<30} {'$' + summary.total_cost_usd:>25} │")

    # By Model
    if summary.by_model:
        click.echo("├" + "─" * 60 + "┤")
        click.echo(f"│ {'By Model':^58} │")
        click.echo("├" + "─" * 60 + "┤")
        for model, stats in summary.by_model.items():
            # Shorten model name for display
            model_short = model.split("-")[1] if "-" in model else model
            model_short = model_short[:15]
            click.echo(f"│ {model_short:<15} │ {stats['calls']:>6} calls │ "
                      f"{stats['input_tokens']:>10,} in │ {stats['output_tokens']:>10,} out │")

    # By Step
    if summary.by_step:
        click.echo("├" + "─" * 60 + "┤")
        click.echo(f"│ {'By Step':^58} │")
        click.echo("├" + "─" * 60 + "┤")
        for step, stats in summary.by_step.items():
            step_short = step[:20] if step else "unknown"
            click.echo(f"│ {step_short:<20} │ {stats['calls']:>5} calls │ "
                      f"${stats['cost_usd']:>10} │")

    click.echo("└" + "─" * 60 + "┘")

    # Recent calls
    if recent > 0:
        recent_usages = await repo.get_recent_usage(limit=recent)
        if recent_usages:
            click.echo()
            click.echo(f"Recent {len(recent_usages)} API calls:")
            click.echo()
            for u in recent_usages:
                model_short = u.model.split("-")[1] if "-" in u.model else u.model
                step = u.step_name or "N/A"
                click.echo(f"  {u.created_at.strftime('%Y-%m-%d %H:%M')} │ "
                          f"{model_short[:10]:<10} │ {step[:15]:<15} │ "
                          f"{u.input_tokens:>6} in │ {u.output_tokens:>6} out │ "
                          f"${u.total_cost_usd}")


@main.command("backfill-bullets")
@click.option("--dry-run", is_flag=True, help="Preview only, don't write to storage")
@click.option("--limit", type=int, default=None, help="Only process first N bullets")
def backfill_bullets(dry_run: bool, limit: Optional[int]):
    """Backfill star_data and tech_stack for bullets missing them.

    Uses Claude Haiku to extract STAR structure and tech stack
    from existing bullet content_en/raw_text.
    """
    asyncio.run(_backfill_bullets(dry_run, limit))


async def _backfill_bullets(dry_run: bool, limit: Optional[int]):
    """Run bullet backfill."""
    from loom.scripts.backfill_bullets import backfill_bullets as do_backfill
    from loom.storage.json_file import JsonFileDataStorage

    storage = JsonFileDataStorage()
    await do_backfill(storage, dry_run=dry_run, limit=limit)


if __name__ == "__main__":
    main()
