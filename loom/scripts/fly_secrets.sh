#!/usr/bin/env bash
# Push the API's configuration from .env into Fly, without any value ever
# appearing on screen, in shell history, or in an argv another process could
# read from `ps`.
#
# `fly secrets import` reads KEY=VALUE lines on stdin, which is why this pipes
# rather than passing `fly secrets set KEY=value` — that form puts every
# secret in the process table.
#
#   loom/scripts/fly_secrets.sh            # push
#   loom/scripts/fly_secrets.sh --list     # names only, no values
set -euo pipefail

cd "$(dirname "$0")/../.."
ENV_FILE=".env"

# Not secrets, or not the API's business:
#   LOOM_API_PORT  — set in fly.toml
#   LOOM_API_URL   — the dashboard's pointer at the API, not used by the API
SKIP="LOOM_API_PORT|LOOM_API_URL"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "no $ENV_FILE here" >&2
  exit 1
fi

names() {
  grep -oE "^[A-Z_][A-Z0-9_]*=" "$ENV_FILE" \
    | sed 's/=$//' \
    | grep -vE "^($SKIP)$" \
    | sort
}

if [[ "${1:-}" == "--list" ]]; then
  echo "Would push these to Fly (names only):"
  names | sed 's/^/  /'
  exit 0
fi

echo "Pushing $(names | wc -l | tr -d ' ') secrets to Fly…"
# Only the lines we mean to send, and only through stdin.
grep -E "^[A-Z_][A-Z0-9_]*=" "$ENV_FILE" \
  | grep -vE "^($SKIP)=" \
  | fly secrets import

echo "Done. Values were never printed; verify names with: fly secrets list"
