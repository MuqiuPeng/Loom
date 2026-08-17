"""Who a request belongs to, carried across the async call stack.

Set once per request from the `X-Loom-User` header (see `AuthMiddleware` in
`loom.api`) and read wherever a `user_id` is needed but not threaded through
the call — chiefly the logger and the `BaseEntity` default. Background work
started with `asyncio.create_task` inherits the caller's context
automatically, so a resume generation kicked off by a request keeps writing
under that request's user.

Lives at the package root rather than under `loom.services` on purpose:
`loom.storage.base` imports it, and `loom.services.__init__` imports the
translator, which imports storage. Anywhere inside `services` and that is a
cycle.
"""

import os
from contextvars import ContextVar

# Empty default so the env var is read at call time — tests and scripts can
# override it after import.
_current_user: ContextVar[str] = ContextVar("loom_current_user", default="")


def get_owner() -> str:
    """The account this installation belongs to.

    Two jobs, and they are the same answer. It is the identity unattended work
    runs as — the CLI, the daily job watcher, the reply poller, none of which
    have a request to inherit from. It is also the account that owns the
    process-level integrations: there is one NOTION_TOKEN, one SMTP identity,
    one outreach table, and they are this person's.

    Stays "local" out of the box so a single-user install and every existing
    script keep working untouched. Set it to the owner's address once the data
    has been migrated to real accounts.
    """
    return os.environ.get("LOOM_DEFAULT_USER_ID", "local")


def set_current_user(user_id: str) -> None:
    """Bind this request (and anything it spawns) to `user_id`."""
    _current_user.set(user_id)


def get_current_user() -> str:
    """The user in scope, or the owner when nothing bound one."""
    return _current_user.get() or get_owner()
