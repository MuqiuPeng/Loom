module.exports = {
  apps: [
    {
      name: "loom-api",
      cwd: "/Users/guanshunpeng/projects/Loom",
      script: "python",
      args: "-m uvicorn loom.api:app --host 0.0.0.0 --port 8001 --timeout-keep-alive 300",
      env: {
        DATABASE_URL: "postgresql+asyncpg://postgres:postgres@localhost:5434/loom",
        LOOM_API_PORT: "8001",
        LOOM_API_KEY: "eYx0uTqgen2PQsJKo5QeDEMGOrmIUmDvYfI1xitp3C8",
      },
    },
    {
      name: "loom-dashboard",
      cwd: "/Users/guanshunpeng/projects/Loom/dashboard",
      script: "./node_modules/.bin/next",
      args: "start --port 3001",
    },
    {
      name: "loom-tunnel",
      script: "/opt/homebrew/bin/cloudflared",
      args: "tunnel --config /Users/guanshunpeng/.cloudflared/loom.yml run loom",
    },
  ],
};
