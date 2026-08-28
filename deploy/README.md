# Production deployment

## Stack

[`docker-compose.prod.yml`](../docker-compose.prod.yml) runs Postgres (internal network only), FastAPI, Next.js (production build), and Caddy. Caddy terminates TLS and routes `/api/*` to the backend and everything else to the frontend.

## Server preparation

1. Install Docker Engine and the Compose plugin.
2. Open inbound TCP **80** and **443** (and SSH). Do not publish Postgres to the internet.
3. Create a deployment directory (for example `/opt/shift-planner`) and copy a production `.env` there (see [Environment](#environment)).
4. Clone this repository into that directory (or point `DEPLOY_REPO_URL` at it for the GitHub Action on first run).

## Environment

Copy [`.env.example`](../.env.example) to `.env` and adjust values. Important keys for production:

| Variable | Purpose |
|----------|---------|
| `PUBLIC_HOST` | Hostname Caddy serves (e.g. `plan.example.com`). Defaults to `localhost` for local trials. |
| `SESSION_SECRET` | Long random secret for session signing. |
| `SESSION_COOKIE_SECURE` | Set `true` when users reach the app over HTTPS (default in compose). |
| `DATABASE_URL` | SQLAlchemy URL pointing at the `postgres` service (see `.env.example`). |
| `BACKEND_CORS_ORIGINS` | Browser origins allowed by the API (comma-separated). For the bundled Caddy layout, use `https://<PUBLIC_HOST>`. |
| `NEXT_PUBLIC_API_BASE_URL` | Leave **empty** for same-host routing (`/api/...` through Caddy). Set to a full API URL if the browser calls a different host. |

Run admin and team-member seed scripts manually when needed (see root [README.md](../README.md)); they are not executed on every container start in production.

## Reverse proxy and TLS

[`Caddyfile`](./Caddyfile) uses `{$PUBLIC_HOST}` as the site address. Caddy obtains certificates automatically for public hostnames when ports 80 and 443 are reachable from the internet.

If the machine has no public inbound ports (CGNAT, strict firewall), run **Cloudflare Tunnel** (`cloudflared`) on the server instead of exposing 80/443, and point the tunnel at `http://caddy:80` on the Compose network (or omit the `caddy` service and point the tunnel at `frontend:3000` / `backend:8000` if you split routing in Cloudflare).

## Cloudflare Tunnel (local development)

For local Docker Compose dev, use a named tunnel to expose localhost (see root [README.md](../README.md#cloudflare-tunnel-for-local-dev) for host ports). Start the stack, then run:

```bash
cloudflared tunnel --protocol http2 run dev-tunnel
```

Point the `dev-tunnel` ingress at `http://localhost:18130` (frontend) and, if needed, `http://localhost:18180` (backend). Update `BACKEND_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` in `.env` when using a public tunnel hostname.

## Cloudflare (DNS you control)

1. Create an **A** (or **AAAA**) record for your app hostname to the server’s public IP, **or** create a Tunnel and use the tunnel’s **CNAME** target.
2. If the hostname is **proxied** (orange cloud), set SSL/TLS mode to **Full** or **Full (strict)** when the origin speaks HTTPS (recommended with Caddy on default HTTPS). Use **Full (strict)** with a valid origin certificate (Caddy’s public certs work when the hostname matches).
3. Optional: enable **Always Use HTTPS**, set a minimum TLS version, and add WAF or Access rules as needed.

## GitHub Actions

- **CI:** [.github/workflows/ci.yml](../.github/workflows/ci.yml) runs on pushes to `main`, pull requests, and merge-queue groups (backend Ruff + pytest, frontend lint, typecheck, build, and a `container-smoke` job that boots `postgres`, `backend`, and `frontend` from `docker-compose.prod.yml`). Pull request jobs merge the latest base branch before those checks. [.github/workflows/refresh-pr-ci.yml](../.github/workflows/refresh-pr-ci.yml) re-runs open same-repo PR checks after each `main` push.
- **Deploy:** [.github/workflows/deploy.yml](../.github/workflows/deploy.yml) runs on `workflow_dispatch` and automatically after the **CI** workflow finishes successfully for `main`. Configure repository secrets:

| Secret | Required | Description |
|--------|----------|-------------|
| `SSH_HOST` | Yes | Server hostname or IP |
| `SSH_USER` | Yes | SSH user |
| `SSH_PRIVATE_KEY` | Yes | Private key for that user (ed25519 recommended) |
| `DEPLOY_PATH` | Yes | Absolute path to the clone on the server |
| `DEPLOY_REPO_URL` | First deploy only | Git clone URL (HTTPS or SSH) when the directory is empty |

The server must already contain a valid `.env` in `DEPLOY_PATH`. The workflow checks out the triggering commit SHA and runs `docker compose -f docker-compose.prod.yml build` and `up -d`. Use a **full** git clone on the server (not `--depth 1`) so `git fetch` can retrieve arbitrary commit SHAs from the remote.

To enforce "no merge before checks", protect `main` in GitHub: require the CI jobs (`backend`, `frontend`, `container-smoke`) and **Require branches to be up to date before merging**. A merge queue is optional and is already wired via the `merge_group` trigger.

## Postgres backups

From the repository root on a host that can run Docker Compose against the production stack:

```bash
sh deploy/scripts/backup-postgres.sh
```

Optional first argument: output file path. Schedule with cron, for example hourly dumps to a persistent directory and sync copies off-server.
