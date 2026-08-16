// PM2 process config for Loom.
//
// Crash guards (min_uptime / max_restarts / exp_backoff_restart_delay) were
// ADDED to every app deliberately: a pm2 app with no restart limit that crashes
// on boot relaunches hundreds of times/sec and hammers macOS launchservicesd
// until the whole machine freezes (this actually happened via CodeBoardGamer's
// flip7). The guards make that impossible — pm2 backs off and finally marks a
// perpetually-failing app "errored" instead of spinning forever.
//
// NOTE: loom-api needs a Python env with uvicorn + the loom package AND Postgres
// on localhost:5434. Until those exist it will just go "errored" (harmless with
// the guards below) — start it only once its deps are in place.
const guards = {
  autorestart: true,
  min_uptime: "10s",
  max_restarts: 10,
  exp_backoff_restart_delay: 500,
};

module.exports = {
  apps: [
    {
      name: "loom-api",
      cwd: "/Users/guanshunpeng/projects/Loom",
      // Absolute path: bare "python" resolves to system python (no uvicorn) under
      // pm2's boot PATH and crashes. anaconda base has uvicorn + the loom package.
      script: "/Users/guanshunpeng/anaconda3/bin/python",
      args: "-m uvicorn loom.api:app --host 0.0.0.0 --port 8001 --timeout-keep-alive 300",
      // DATABASE_URL deliberately NOT set here. load_dotenv() does not
      // override variables that already exist in the environment, so anything
      // pm2 injects silently wins over .env — which is how the app kept
      // talking to the old local Postgres for a while after the database was
      // migrated to Supabase, with no error to show for it. Let .env be the
      // single source of truth.
      env: {
        LOOM_API_PORT: "8001",
        LOOM_API_KEY: "eYx0uTqgen2PQsJKo5QeDEMGOrmIUmDvYfI1xitp3C8",
      },
      ...guards,
    },
    {
      name: "loom-dashboard",
      cwd: "/Users/guanshunpeng/projects/Loom/dashboard",
      script: "./node_modules/.bin/next",
      args: "start --port 3001",
      ...guards,
    },
    {
      name: "loom-tunnel",
      script: "/opt/homebrew/bin/cloudflared",
      args: "tunnel --config /Users/guanshunpeng/.cloudflared/loom.yml run loom",
      ...guards,
    },
  ],
};
