# AI ATS Resume Optimiser

An explainable ATS scoring and resume optimisation engine with LaTeX support.
Built around one rule: **propose edits to the source, score the result** — and
never invent a fact to raise a score.

- [`ats-resume-optimizer-architecture.md`](ats-resume-optimizer-architecture.md)
  — product, system design, scoring model, roadmap.
- [`apps/web`](apps/web) — Next.js landing page and intake UI.
- [`apps/api`](apps/api) — FastAPI gateway and Phase 1 engine.
- [`infra/docker-compose.yml`](infra/docker-compose.yml) — Postgres + Redis + API.

## Run the backend

```bash
cd apps/api
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

Docs: <http://localhost:8000/docs>. See [`apps/api/README.md`](apps/api/README.md)
for endpoints, scoring details, guardrails, and the exact implementation status.

## Run the frontend

Start the backend first, then:

```bash
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

<http://localhost:3000>. The `/start` flow uploads the resume, analyses the job
description, scores it, and starts an optimisation job through a same-origin
proxy at `/api/backend/*`. Set `API_BASE_URL` (default
`http://127.0.0.1:8000`) and, if the engine has a key configured, set
`ATS_API_KEY` on the Next server to the same value. Keep `ATS_API_KEY`
server-side — do not rename it with a `NEXT_PUBLIC_` prefix.

If the engine is not running, the intake UI shows the connection error instead
of a fake result.

## Run everything in Docker

```bash
docker compose -f infra/docker-compose.yml up --build
```

## Verify the backend

```bash
cd apps/api
uv run pytest -q
uv run ruff check app tests
```
