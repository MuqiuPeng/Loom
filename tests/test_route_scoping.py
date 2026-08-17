"""Every route that touches user data must declare who is asking.

This is the structural half of multi-user. The isolation in
test_multi_user.py proves the endpoints that exist today are scoped; this
proves the *next* one will be, because forgetting `user_id` is not a mistake
anything else catches — the endpoint works perfectly, against the wrong
account, and only in production with two users signed in.

Adding an endpoint under one of the user-data prefixes therefore has exactly
two legal outcomes: it takes `current_user` (or `require_owner`, which is
built on it), or its path is listed in UNSCOPED below with a reason.
"""

import pytest
from fastapi.routing import APIRoute

from loom.api import app
from loom.deps import current_user, require_owner

# Route prefixes whose responses are somebody's private data.
USER_DATA_PREFIXES = (
    "/api/profile",
    "/api/resumes",
    "/api/jobs",
    "/api/tasks",
    "/api/workflow",
    "/api/scout",
    "/api/logs",
    "/api/chat",
)

# Deliberate exceptions. Each entry is a promise that the route either exposes
# nothing user-specific or carries its own proof of authorisation.
UNSCOPED: dict[tuple[str, str], str] = {
    ("GET", "/api/resumes/{resume_id}/pdf"):
        "Dual-auth: a per-artifact HMAC signature authorises the Notion link, "
        "and the handler scopes by user whenever it is the Bearer key instead.",
    ("POST", "/api/workflow/run"):
        "Runs a workflow definition by name against the trigger's own context; "
        "persists nothing under a user.",
    ("POST", "/api/workflows/{run_id}/retry"):
        "Returns 501 — workflow run persistence does not exist yet.",
    ("POST", "/api/resumes/render"):
        "Stateless render of a caller-supplied context.",
    ("GET", "/api/scout/areas"):
        "Static list of suburb suggestions.",
    ("GET", "/api/scout/templates"):
        "Static list of email formats.",
    ("POST", "/api/scout/search"):
        "Queries Google and the candidates' own sites; saves nothing.",
    ("POST", "/api/scout/survey"):
        "Same, for an area sweep.",
}

IDENTITY_DEPENDENCIES = {current_user, require_owner}


def user_data_routes() -> list[tuple[str, str, APIRoute]]:
    found = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith(USER_DATA_PREFIXES):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            found.append((method, route.path, route))
    return sorted(found, key=lambda r: (r[1], r[0]))


def declares_identity(route: APIRoute) -> bool:
    return any(
        d.call in IDENTITY_DEPENDENCIES
        for d in route.dependant.dependencies
    )


@pytest.mark.parametrize(
    "method,path,route",
    user_data_routes(),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_route_is_scoped_to_a_user(method, path, route):
    if (method, path) in UNSCOPED:
        pytest.skip(UNSCOPED[(method, path)])
    assert declares_identity(route), (
        f"{method} {path} touches user data but takes no current_user "
        f"dependency. Add `user_id: str = CurrentUser` (or `owner: str = "
        f"OwnerOnly`) to its signature and pass it down to storage — or, if "
        f"it genuinely exposes nothing user-specific, add it to UNSCOPED in "
        f"{__file__} with the reason."
    )


def test_unscoped_list_has_no_stale_entries():
    """A route that was removed or renamed should not keep its exemption."""
    live = {(m, p) for m, p, _ in user_data_routes()}
    stale = set(UNSCOPED) - live
    assert not stale, f"UNSCOPED lists routes that no longer exist: {sorted(stale)}"


def test_there_are_routes_to_check():
    """Guards against the prefixes drifting and this file silently passing."""
    assert len(user_data_routes()) > 30
