# Loom

Resume tailoring (Notion job tracker → generated CV → signed PDF back to the
row) plus Company Scout / Freelance outreach. Single maintainer; `git log` is
the design record, and commit messages here are deliberately long because of
it. This file is the part that does not fit in a commit: the shape of the
running system, and the decisions that look like bugs later.

## Where things run

| Piece | Runs on | Notes |
|---|---|---|
| API (FastAPI) | **Fly.io**, app `loom-api`, region `syd` | `Dockerfile` + `fly.toml` |
| Dashboard (Next) | **Vercel**, project `dashboard` | `loom.robindev.org` |
| Database | **Supabase** Postgres, `syd`, via the pooler | migrations with alembic |
| `loom-api.robindev.org` | DNS A/AAAA → Fly | grey cloud, see below |
| `/demo/<slug>` | Vercel → Supabase directly | survives the API being down |

Nothing production depends on the laptop. pm2 still runs `loom-api` locally for
development, and `loom-tunnel` is stopped — it existed only to publish the API
from this machine and has no job now.

The acceptance test for any deploy change is: **stop the local pm2 processes
and confirm the site still works.** That is the property that was bought here;
anything that quietly reintroduces the dependency has broken it.

## Deploying

```bash
# API
fly deploy --remote-only --ha=false        # --ha=false: one machine, see below
loom/scripts/fly_secrets.sh                # .env → fly secrets, via stdin
loom/scripts/fly_secrets.sh --list         # names only

# Dashboard
cd dashboard && vercel --prod --yes        # env changes need a redeploy

# Migrations (hits the real Supabase — env.py loads .env)
python -m alembic upgrade head
```

Fly's gh/vercel/fly CLIs are authenticated. **`gh` has two accounts**: the
default config is `RobinDev-Peng` (read-only on this repo); the one that can
open and merge PRs is `MuqiuPeng`, under a separate config dir:

```bash
GH_CONFIG_DIR=~/.config/gh-guanshunpeng gh pr view 1
```

## Decisions that look like mistakes

Each of these has been "fixed" back the wrong way at least once, or is one
glance away from it.

- **The DNS records for `loom-api` are grey cloud, not proxied.** Fly issues
  and renews its own certificate. Proxying through Cloudflare puts a second
  TLS layer in front and `fly certs check` never leaves `Not verified`.

- **`fly.toml` does not scale to zero.** The lifespan hook starts the daily
  job-tracker run and the hourly reply poller. Neither runs on a sleeping
  machine, and the outreach signature undertakes to action an opt-out within
  five business days — a poller that only wakes on traffic is not a mechanism.

- **One machine (`--ha=false`, `min_machines_running = 1`).** Those same
  schedulers must not run twice, and the chat session store is in-process.

- **`LOOM_SIGNING_SECRET` is separate from `LOOM_API_KEY`.** Signed PDF links
  are *published* — they sit in Notion rows for months — while the API key
  must stay rotatable. Deriving one from the other means every rotation
  silently breaks every link ever handed out. Rotating the signing secret is
  now a deliberate act meaning "invalidate everything outstanding"; when you
  do, run `python -m loom.scripts.resign_notion_links` (idempotent).

- **`.gitignore` anchors `/lib/`, not `lib/`.** Unanchored, it matched
  `dashboard/lib` at any depth and had silently excluded the API client, the
  types and `auth.ts` — the sign-in allowlist itself — from every commit ever
  made. Same class of bug as `.env.*`: an ignore rule that is too broad fails
  silently and forever.

- **Chinese markets are configured but refuse to search.** `config/scout_areas.json`
  lists CN areas with `provider: "amap"`, which is not implemented, so a search
  there returns 501. The fallback would be Google, and Google's answer for
  Wuzhen is not a worse answer — it is a meaningless one. The areas stay listed
  because the research outlives the integration; the UI greys them out.

## Invariants

- **One source per credential.** `DATABASE_URL` holds the DB password; there is
  no `SUPABASE_PASSWORD` any more. Two copies drift: the API spent an unknown
  amount of time authenticating with a stale password that only worked because
  one Supabase pooler node had the old secret cached. Nothing errored until a
  request landed on a different node.
- **Secrets never enter a commit.** `ecosystem.config.js` used to inline
  `LOOM_API_KEY` in this public repo. It is `.env` only now, and `.env.*` is
  ignored wholesale.
- **`~/env/DNS_TOKEN`** is the Cloudflare token to use — zone `DNS Write` on
  `robindev.org` only. The other token in that file is account-wide and should
  not be used for this.
- **Every route under `/api/profile|resumes|jobs|tasks|workflow|scout|logs|chat`
  declares a `current_user` dependency.** `tests/test_route_scoping.py` enforces
  it with an explicit exemption list. Forgetting `user_id` is invisible
  otherwise: the endpoint works perfectly, against the wrong account.
- **The outreach pipeline only runs on `kind="freelance"` leads.** A job-hunt
  lead reaching harvest → demo → draft → send would put a commercial pitch,
  signed with the user's business name, in the inbox of a company he wanted to
  work for. Different messages, different law. `_require_lead(..., kind=...)`
  answers 409 rather than filtering.

## Verifying a change

```bash
python -m pytest tests -q          # 65 tests; route-scoping guard lives here
cd dashboard && npx tsc --noEmit && npm test    # 13 vitest cases
```

```bash
python -m loom.scripts.check_deployed   # what is committed but not yet running

python -m loom.cli scout doctor         # could outreach run, and what would happen
python -m loom.cli scout leads          # every lead and what has been done to it
python -m loom.cli scout show <name>    # findings, harvest, who may be written to
python -m loom.cli scout draft <name>   # the email that would go — renders only
```

There is deliberately no `scout send`. A message reaching a stranger goes
through a person marking a row Approved in Notion and then the endpoint; a
second path is the route around that the redirect's own note warns about.

CI runs the checks on every push and deploys nothing, so the repository and the
running system drift apart quietly — `check_deployed` is what says by how much.
It reports and never acts; the database half of it is exact, the two code
halves compare timestamps because neither platform records a commit.

`tests/test_multi_user.py` covers isolation between two accounts;
`dashboard/lib/acting-user.test.ts` covers which account a proxied request acts
as — a bug there served a signed-in user somebody else's profile, one hop
earlier than anything the Python suite can see.

For anything touching deploy or credentials, the check that matters is the
end-to-end one: stop `loom-api` locally and confirm `loom.robindev.org` and a
real signed PDF link from Notion both still answer.
