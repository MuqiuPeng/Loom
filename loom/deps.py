"""FastAPI dependencies for request identity.

Separate from `loom.current_user` (which must stay import-light, since
`loom.storage.base` depends on it) and from `loom.api` (which imports the
chat router, so the router cannot import back).
"""

from fastapi import Depends, Header, HTTPException

from loom.current_user import get_current_user, get_owner, set_current_user

USER_HEADER = "X-Loom-User"


async def current_user(x_loom_user: str | None = Header(default=None)) -> str:
    """The account this request acts as.

    The Bearer key authenticates the *caller* (the dashboard's server-side
    proxy, the CLI); this header says which of its users the call is for. The
    proxy sets it from the signed NextAuth session, so a browser cannot forge
    it — it never reaches the API directly, and the key it would need to do so
    is server-side only.

    Callers that send no header — CLI, cron, scripts — get the owner rather
    than an error, which keeps single-user installs working.
    """
    user_id = x_loom_user or get_current_user()
    # Endpoints run in this task, as does anything they hand to
    # asyncio.create_task, so binding here covers background work too.
    set_current_user(user_id)
    return user_id


CurrentUser = Depends(current_user)


async def require_owner(user_id: str = Depends(current_user)) -> str:
    """Gate the features that are the installation's, not an account's.

    Notion and outreach run on process-level config: one NOTION_TOKEN, one
    mirror page, one job-tracker database, one SMTP identity. There is no
    per-user version of them, so a second account calling these does not get
    its own — it acts on the owner's. Syncing would overwrite the owner's
    Notion profile mirror with its own; send-approved would put real mail in
    real inboxes over the owner's signature.

    403 rather than a silent no-op: the caller asked for something real, and
    the answer is that this feature has one owner.
    """
    if user_id != get_owner():
        raise HTTPException(
            status_code=403,
            detail=(
                "This feature is tied to the installation owner's Notion and "
                "email configuration and cannot act on behalf of another account."
            ),
        )
    return user_id


OwnerOnly = Depends(require_owner)
