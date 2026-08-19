"""An endpoint the dashboard calls without a body must accept one without.

The panel's Draft button posted no JSON and the endpoint declared a required
one, so it answered 422 from the day it was added. Nothing caught it: the
route existed, the client compiled, every check passed, and the only drafts in
the database had been made from scripts. The button had never worked.

This is the structural half. Rather than assert one endpoint's behaviour, it
asserts the rule that would have prevented it — a request model whose every
field has a default describes an optional body, and an endpoint that declares
it without a default contradicts its own model.

Where that contradiction is deliberate, the path goes in REQUIRED_ANYWAY with
the reason, which is the same shape test_route_scoping uses for its
exemptions.
"""

import inspect

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from loom.api import app

# Endpoints whose body stays required even though every field has a default,
# because an empty body would do something rather than nothing.
REQUIRED_ANYWAY = {
    # A default-parameter search is a real, billable Google Places call. A 422
    # on a malformed request is cheaper than a search nobody asked for.
    "/api/scout/search",
    "/api/scout/survey",
    # An empty PATCH would write nothing; requiring the body keeps a
    # misspelled field an error rather than a silent no-op.
    "/api/scout/leads/{lead_id}",
}


def _body_params(endpoint) -> list[tuple[str, type, bool]]:
    """(name, model, has_default) for each Pydantic body parameter."""
    out = []
    for name, param in inspect.signature(endpoint).parameters.items():
        annotation = param.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            out.append((name, annotation, param.default is not inspect.Parameter.empty))
    return out


def _all_fields_defaulted(model: type[BaseModel]) -> bool:
    return bool(model.model_fields) and all(
        not field.is_required() for field in model.model_fields.values()
    )


ROUTES = [
    (route.path, route.endpoint)
    for route in app.routes
    if isinstance(route, APIRoute) and route.methods & {"POST", "PATCH", "PUT"}
]


@pytest.mark.parametrize("path,endpoint", ROUTES, ids=[p for p, _ in ROUTES])
def test_optional_models_have_optional_bodies(path, endpoint):
    for name, model, has_default in _body_params(endpoint):
        if not _all_fields_defaulted(model):
            continue
        if path in REQUIRED_ANYWAY:
            continue
        assert has_default, (
            f"{path} takes {name}: {model.__name__}, whose fields all have "
            f"defaults, but declares it without one — a caller that sends no "
            f"body gets 422. Give it `= {model.__name__}()`, or list the path "
            f"in REQUIRED_ANYWAY with the reason."
        )


def test_draft_accepts_no_body():
    """The specific one that was broken, kept as a regression."""
    from loom.api import DraftRequest, draft_scout_outreach

    name, model, has_default = _body_params(draft_scout_outreach)[0]
    assert model is DraftRequest
    assert has_default, "the Draft button sends no body"
