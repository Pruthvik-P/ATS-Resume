# AI ATS Resume Optimiser

An explainable ATS scoring and resume optimisation engine with LaTeX support.
Built around one rule: **propose edits to the source, score the result** — and
never invent a fact to raise a score.

- [`ats-resume-optimizer-architecture.md`](ats-resume-optimizer-architecture.md)
  — product, system design, scoring model, roadmap.
- [`apps/web`](apps/web) — Next.js landing page and intake UI.
- [`apps/api`](apps/api) — FastAPI gateway and Phase 1 engine.
- [`pending.md`](pending.md) — remaining work against the architecture doc.
- [`infra/docker-compose.yml`](infra/docker-compose.yml) — Postgres + Redis + API + web UI + LaTeX worker.
- [`services/latex_worker`](services/latex_worker) — sandboxed TeX Live compile worker.

## Quick start: run everything in Docker

Requirements: Docker with Compose v2 (Docker Desktop on Windows/macOS). Python
and Node are **not** needed on the host — both run inside the containers.

First run (builds the images, then starts Postgres, the LaTeX worker, the API, and the UI):

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

Wait until `postgres`, `latex_worker`, `api`, and `web` report `(healthy)`:

```bash
docker compose -f infra/docker-compose.yml ps
```

Then open **<http://localhost:3000/start>**.

| Service | Address | Notes |
|---|---|---|
| Web UI | <http://localhost:3000> | Next.js; browser calls `/api/backend/*` on this origin |
| API | <http://localhost:8000> · [docs](http://localhost:8000/docs) | FastAPI; runs `alembic upgrade head` on boot |
| Postgres | `localhost:5432` | user/password/database: `ats` / `ats` / `ats` |
| Redis | `localhost:6379` | reserved for Phase 2; the API does not use it yet |
| LaTeX worker | internal only | sandboxed compile worker; enable with `ATS_LATEX_COMPILE_ENABLED=true` |

### Day-to-day commands

```bash
# Start an existing build (no rebuild)
docker compose -f infra/docker-compose.yml up -d

# Rebuild after changing code, then restart
docker compose -f infra/docker-compose.yml up -d --build

# Follow logs (one or all services)
docker compose -f infra/docker-compose.yml logs -f web api

# Stop, keeping the database and uploaded resumes
docker compose -f infra/docker-compose.yml down

# Stop and delete the database + uploads volumes
docker compose -f infra/docker-compose.yml down -v
```

The first build takes a few minutes (it installs Python and npm dependencies and
runs `next build`). Later builds reuse the dependency layers and only recompile
what changed.

### How the containers connect

The browser never talks to the API directly. It calls the same-origin proxy at
`/api/backend/*` on port 3000, and the `web` container forwards allowlisted
routes to `http://api:8000` over the Compose network. `API_BASE_URL` and
`ATS_API_KEY` stay server-side in the `web` container.

Resumes are stored in the `uploads` volume and rows in `pgdata`, so `down`
preserves both; only `down -v` deletes them.

### Optional: protect the engine with a shared key

Set `ATS_API_KEY` before starting — the same value is injected into both the API
and the web proxy:

```powershell
# PowerShell
$env:ATS_API_KEY = "change-me"
docker compose -f infra/docker-compose.yml up -d --build
```

```bash
# bash / zsh
export ATS_API_KEY=change-me
docker compose -f infra/docker-compose.yml up -d --build
```

You can also copy [`infra/.env.example`](infra/.env.example) to `infra/.env` and
put `ATS_API_KEY=...` there; Compose reads it automatically. Do not prefix it
with `NEXT_PUBLIC_`.

### Optional: enable sandboxed LaTeX compilation

The `latex_worker` service is built and started with the stack, but compilation
is opt-in because TeX Live is heavy and a compile adds latency to uploads:

```powershell
$env:ATS_LATEX_COMPILE_ENABLED = "true"
docker compose -f infra/docker-compose.yml up -d --build
```

The worker runs read-only, non-root, with dropped capabilities and CPU/memory/PID
limits, and is reachable only over an internal Compose network. When it is
unavailable, uploads continue with static LaTeX analysis and record
`compile_status: unavailable`.

## Local development (optional)

Use this when you want hot reload and a debugger. Run the backend and frontend
in separate terminals.

### Backend

```bash
cd apps/api
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

Docs: <http://localhost:8000/docs>. See [`apps/api/README.md`](apps/api/README.md)
for endpoints, scoring details, guardrails, and the exact implementation status.

### Frontend

Start the backend first, then:

```bash
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

<http://localhost:3000>. The `/start` flow uploads the resume, analyses the job
description, scores it, and starts an optimisation job through the same-origin
proxy at `/api/backend/*`. Set `API_BASE_URL` (default
`http://127.0.0.1:8000`) and, if the engine has a key configured, set
`ATS_API_KEY` on the Next server to the same value. Keep `ATS_API_KEY`
server-side — do not rename it with a `NEXT_PUBLIC_` prefix.

If the engine is not running, the intake UI shows the connection error instead
of a fake result.


## Verify the backend

```bash
cd apps/api
uv run pytest -q
uv run ruff check app tests
```
