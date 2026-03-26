"""Resume-tailor workflow definition."""

from loom.storage import TriggerType, WorkflowDefinition

# Workflow definition
RESUME_TAILOR_WORKFLOW = WorkflowDefinition(
    name="resume-tailor",
    description="Parse JD, match profile, select bullets, generate tailored resume",
    trigger_type=TriggerType.MANUAL,
    steps=[
        {"name": "parse-jd", "order": 0, "config": {}},
        {"name": "match-profile", "order": 1, "config": {}},
        {"name": "select-bullets", "order": 2, "config": {}},
        {"name": "generate-resume", "order": 3, "config": {}},
    ],
    is_active=True,
)


def get_workflow() -> WorkflowDefinition:
    """Get the resume-tailor workflow definition."""
    return RESUME_TAILOR_WORKFLOW


async def register(storage: "WorkflowStorage | None" = None) -> WorkflowDefinition:
    """Register the resume-tailor workflow to storage if it doesn't exist.

    Args:
        storage: Optional storage backend. If None, returns definition without persisting.

    Returns:
        The workflow definition
    """
    if storage is None:
        return RESUME_TAILOR_WORKFLOW

    # TODO: Check if exists and create if not
    # For now, just return the definition
    return RESUME_TAILOR_WORKFLOW
