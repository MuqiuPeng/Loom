"""Say what is committed but not yet running.

Deploying here is deliberate: `fly deploy` and `vercel --prod` are run by a
person who has decided a change should go live, and CI is verification only. The
cost of that arrangement is that the repository and the running system drift
apart silently. It happened during the afternoon this was written — a commit
changing how demo URLs are minted sat pushed and green for twenty minutes while
production served the previous code, and nothing anywhere said so.

This reports the gap. It does not close it. Running a deploy from a script that
was only asked a question is exactly the automation the workflow file refuses
to have, and for the same reason.

HOW IT KNOWS, and what that is worth. Neither platform records a commit: both
deploys upload a working tree, so there is no sha on the other end to compare
against. What there is on both sides is a timestamp, so the question asked is
"has anything touching this target been committed since it was last deployed",
which is a good enough proxy and an honest one. Its limits, stated rather than
discovered:

  * a deploy from a dirty or stale working tree looks current here
  * a commit that changes nothing meaningful still reads as drift
  * clock skew between a laptop and a platform's API is not corrected for

The database is the exception and is checked exactly, because alembic does
record what has been applied. That comparison is worth more than the other two
together: code arriving before its migration is an inconvenience, and a
migration arriving before the code that needs it can be an outage.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

# By path, not by search. alembic's env.py loads this file and a first version
# of this script did not, so the two asked different databases what version
# they were at and disagreed by eight migrations — the script's first ever
# output was a gap that did not exist. A bare load_dotenv() walks up from the
# calling frame and does not resolve to the repository root under `python -m`,
# which is a subtle enough failure that a script whose whole job is comparing
# two things should not rely on it to find one of them.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Paths whose contents ship to each target. Deliberately generous — a
# false "you have something to deploy" costs a glance, and a missed one
# costs the afternoon this script exists because of.
TARGETS: list[tuple[str, list[str]]] = [
    (
        "API (Fly)",
        ["loom/", "config/", "Dockerfile", "fly.toml", "pyproject.toml", "alembic.ini"],
    ),
    ("Dashboard (Vercel)", ["dashboard/"]),
]


def _run(*args: str, stderr: bool = False) -> str:
    """Run a command, returning stdout — or both streams when asked.

    `stderr=True` exists for the Vercel CLI, which prints everything a human
    reads to stderr and keeps stdout for the machine-readable remainder.
    """
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise RuntimeError(f"{args[0]}: {e}") from e
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip()[:200])
    return (out.stdout + out.stderr) if stderr else out.stdout


def fly_deployed_at() -> datetime:
    payload = json.loads(_run("fly", "releases", "--app", "loom-api", "--json"))
    live = [r for r in payload if r.get("Status") == "complete"]
    if not live:
        raise RuntimeError("no complete release")
    return datetime.fromisoformat(live[0]["CreatedAt"].replace("Z", "+00:00"))


def vercel_deployed_at() -> datetime:
    """When the newest deployment was created.

    `vercel ls` prints its table to stderr and only the bare URLs to stdout —
    a piped invocation therefore returns a list of addresses and no timestamps,
    which is how a first attempt at this concluded there were no deployments at
    all. The URLs are the useful half anyway: the first is the newest, and
    `vercel inspect` gives it an exact creation time rather than the table's
    rounded "4h".
    """
    urls = [u for u in _run("vercel", "ls", "dashboard").split() if u.startswith("http")]
    if not urls:
        raise RuntimeError("no deployments listed")
    for line in _run("vercel", "inspect", urls[0], stderr=True).splitlines():
        if line.strip().startswith("created"):
            # "Mon Aug 17 2026 14:25:26 GMT+1000 (...)  [28m ago]" — cut the
            # trailing zone name and the age note, both unparseable.
            stamp = line.split("created", 1)[1].split("(")[0].strip()
            return datetime.strptime(stamp, "%a %b %d %Y %H:%M:%S GMT%z").astimezone(UTC)
    raise RuntimeError("no creation time on the newest deployment")


def commits_since(when: datetime, paths: list[str]) -> list[str]:
    out = _run(
        "git",
        "log",
        f"--since={when.isoformat()}",
        "--format=%h %ad %s",
        "--date=format:%m-%d %H:%M",
        "--",
        *paths,
    )
    return [line for line in out.splitlines() if line.strip()]


def uncommitted(paths: list[str]) -> list[str]:
    out = _run("git", "status", "--porcelain", "--", *paths)
    return [line for line in out.splitlines() if line.strip()]


async def migration_gap() -> tuple[str, str]:
    """(applied on the database, head in the repository)."""
    from sqlalchemy import text

    from loom.storage.database import get_session

    head = ""
    for line in _run("python", "-m", "alembic", "heads").splitlines():
        if line.strip():
            head = line.split()[0]
    async with get_session() as session:
        result = await session.execute(text("select version_num from alembic_version"))
        return (result.scalar() or "none", head)


async def main() -> int:
    drifted = False
    print("What is committed but not yet running\n")

    for name, paths in TARGETS:
        deployed_at = fly_deployed_at if name.startswith("API") else vercel_deployed_at
        try:
            when = deployed_at()
        except Exception as e:
            print(f"  {name}: could not ask the platform — {e}")
            continue

        ahead = commits_since(when, paths)
        dirty = uncommitted(paths)
        age = (datetime.now(UTC) - when).total_seconds() / 3600
        print(f"  {name} — deployed {age:.1f}h ago")
        if ahead:
            drifted = True
            print(f"      {len(ahead)} commit(s) since:")
            for line in ahead:
                print(f"        {line}")
        if dirty:
            drifted = True
            print(f"      {len(dirty)} uncommitted file(s):")
            for line in dirty[:6]:
                print(f"        {line}")
        if not ahead and not dirty:
            print("      up to date")
        print()

    try:
        applied, head = await migration_gap()
    except Exception as e:
        print(f"  Database: could not be read — {e}")
        return 1 if drifted else 0

    # The one comparison that is exact, and the one where the order matters.
    if applied == head:
        print(f"  Database — at {applied}, matching the repository")
    else:
        drifted = True
        print(f"  Database — applied {applied}, repository head {head}")
        print("      run: python -m alembic upgrade head")

    print()
    print("Nothing here deploys anything. To close a gap:")
    print("  fly deploy --remote-only --ha=false")
    print("  cd dashboard && vercel --prod --yes")
    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
