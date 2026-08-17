"""Send and read mail through Lark's API, via lark-cli.

An alternative transport to mailer.py's SMTP and inbox.py's IMAP, chosen
because the Lark mailbox is authorised already and needs neither an app
password nor the admin toggle that gates third-party clients.

Driving the CLI rather than calling the REST API directly is deliberate. The
CLI already holds the OAuth tokens and refreshes them; reimplementing that in
Python would mean a second copy of the refresh logic, and a token that expires
at three in the morning is exactly the thing a background poller must not
depend on twice over.

The public surface deliberately matches the SMTP/IMAP one so mailer.send and
inbox.fetch_replies can dispatch between them. Nothing above this module
should know which transport is in use.

Two things the CLI does that will bite a naive caller:

  * it prints human "tip:" lines to stdout ahead of the JSON, and one of those
    tips contains a brace, so scanning for the first "{" lands inside the tip
    rather than at the payload
  * `+send` saves a draft unless --confirm-send is passed, so a caller that
    forgets it reports success while nothing was sent
"""

import asyncio
import json
import os
import shutil
from typing import Any

# The profile holding the Lark (international) app, kept separate from the
# feishu one so neither login disturbs the other.
PROFILE = os.environ.get("LARK_CLI_PROFILE", "lark-intl")

# pm2 starts the API with a login-less PATH that does not include nvm's bin
# directory, so resolving the binary by name works in a terminal and fails
# under the process manager. Look it up properly, and let an env var win.
_CANDIDATES = (
    os.path.expanduser("~/.nvm/versions/node/v24.16.0/bin/lark-cli"),
    "/usr/local/bin/lark-cli",
    "/opt/homebrew/bin/lark-cli",
)

QUIET = {
    "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
    "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1",
}


class LarkMailError(RuntimeError):
    pass


def cli_path() -> str:
    explicit = os.environ.get("LARK_CLI")
    if explicit and os.path.exists(explicit):
        return explicit
    found = shutil.which("lark-cli")
    if found:
        return found
    for candidate in _CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return ""


def available() -> bool:
    return bool(cli_path())


def parse_output(text: str) -> dict:
    """The JSON payload, ignoring whatever the CLI printed above it.

    Scanning for the first brace is wrong: one of the CLI's tip lines embeds
    a JSON example, so that lands mid-sentence. Only a line that *starts* with
    a brace begins the payload.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(("{", "[")):
            try:
                return json.loads("\n".join(lines[index:]))
            except json.JSONDecodeError:
                continue
    raise LarkMailError(f"no JSON in output: {text[:300]}")


async def run(*args: str, timeout: float = 60.0) -> dict:
    """One lark-cli call, returning its parsed payload."""
    binary = cli_path()
    if not binary:
        raise LarkMailError(
            "lark-cli not found — set LARK_CLI to its absolute path"
        )
    process = await asyncio.create_subprocess_exec(
        binary, "--profile", PROFILE, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **QUIET},
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        raise LarkMailError(f"lark-cli timed out after {timeout}s") from None

    text = out.decode(errors="replace")
    if process.returncode != 0:
        # Errors go to stderr as their own envelope; surface the message
        # rather than a bare exit code.
        detail = err.decode(errors="replace") or text
        try:
            body = parse_output(detail)
            message = (body.get("error") or {}).get("message") or detail
        except LarkMailError:
            message = detail
        raise LarkMailError(f"lark-cli {' '.join(args[:2])}: {message[:300]}")
    return parse_output(text)


async def address() -> str:
    """The mailbox this profile is authorised against."""
    body = await run(
        "mail", "user_mailboxes", "profile",
        "--params", '{"user_mailbox_id":"me"}',
    )
    return ((body.get("data") or {}).get("primary_email_address")) or ""


async def send(
    to: str, subject: str, body: str, html: str = "",
    inline: list[dict[str, str]] | None = None,
) -> str:
    """Send one message. Returns whatever id Lark reports.

    `html` is a rendering of `body`, not a different message. When supplied it
    is what goes out; the plain text remains the source the wording came from.

    --confirm-send is not optional: without it the CLI files a draft and
    returns success, which would have the queue marking rows Sent for mail
    nobody received.

    --no-signature likewise: Loom's body already carries its own sign-off and
    the Spam Act opt-out line, and Lark would append a second signature under
    them.
    """
    # Lark refuses absolute paths, so every inline file has to be handed over
    # as a path relative to the working directory.
    args = [
        "mail", "+send",
        "--to", to,
        "--subject", subject,
        "--body", html or body,
        "--no-signature",
        "--confirm-send",
        "--format", "json",
    ]
    if not html:
        args.insert(-4, "--plain-text")
    if inline:
        args += ["--inline", json.dumps(inline)]
    payload = await run(*args)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("message_id", "id", "draft_id"):
        value = (data or {}).get(key)
        if value:
            return str(value)
    return ""


async def recent(days: int, limit: int) -> list[dict[str, Any]]:
    """Summaries of recent inbox mail, newest first."""
    payload = await run(
        "mail", "+triage",
        "--max", str(max(1, min(limit, 400))),
        "--filter", json.dumps({"folder": "INBOX"}),
        "--format", "json",
    )
    return payload.get("messages") or []


async def message(message_id: str) -> dict[str, Any]:
    """One message with its body."""
    payload = await run(
        "mail", "+message",
        "--message-id", message_id,
        # HTML, not plain text: Lark's plain-text projection has every newline
        # stripped, and the reply reader needs the line structure to tell a
        # person's own words from the quote below them.
        "--html=true",
        "--format", "json",
    )
    data = payload.get("data")
    return data if isinstance(data, dict) else payload
