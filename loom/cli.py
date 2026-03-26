"""Loom CLI - command line interface for running workflows."""

import asyncio
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
def run_resume(jd: Optional[str], jd_file: Optional[str], lang: str, output_dir: str, seed: bool):
    """Run the resume-tailor workflow.

    Provide JD text directly with --jd or from a file with --jd-file.
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
    click.echo(f"  JD length: {len(jd_text)} chars")
    if seed:
        click.echo("  Seeding sample profile data...")
    click.echo()

    asyncio.run(_run_resume_workflow(jd_text, lang, output_dir, seed))


async def _run_resume_workflow(jd_text: str, lang: str, output_dir: str, seed: bool = False):
    """Execute the resume-tailor workflow."""
    from loom.core import WorkflowRunner, step_registry
    from loom.storage import InMemoryDataStorage
    from loom.storage.init_db import get_storage, get_workflow_definitions, init_db
    from loom.triggers import ManualTrigger

    # Import steps to register them
    import loom.steps  # noqa: F401

    # Initialize storage
    storage = await init_db()

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

            # Create step with shared storage
            step_class = step_classes.get(step_name)
            if step_class:
                # Inject storage for steps that need it
                if step_name in ["match-profile", "select-bullets", "generate-resume"]:
                    step = step_class(storage=storage)
                else:
                    step = step_class()
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


if __name__ == "__main__":
    main()
