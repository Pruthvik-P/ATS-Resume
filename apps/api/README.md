# ATS Engine API

FastAPI gateway and Phase 1 engine for the AI ATS resume scorer and optimiser.
The product and system design live in
[`ats-resume-optimizer-architecture.md`](../../ats-resume-optimizer-architecture.md).

## What works today

| Capability | Status |
|---|---|
| Upload PDF / DOCX / `.tex` / `.tex` zip | Implemented |
| Heuristic structuring to a JSON Resume subset | Implemented |
| LaTeX static analysis (ATS risks + hostile-input checks) | Implemented |
| JD analysis (must/nice skills, seniority, years, knock-outs) | Implemented |
| Seven-component explainable scoring with caps and penalties | Implemented |
| Truthfulness-constrained optimisation proposals + accept/reject | Implemented |
| Facts Bank | Implemented |
| PostgreSQL + Alembic schema | Implemented |
| Sandboxed LaTeX compile + PDF parse-fidelity comparison | Not yet (Phase 2) |
| OCR for scanned PDFs | Not yet (Phase 2) |
| Trained embeddings / pgvector search | Not yet (Phase 2) — see `HashedEmbedder` |
| Celery/Temporal worker | Not yet — jobs run in-process |
| LLM rewriting | Pluggable; ships as a deterministic stub |
| DOCX export, versioned file patching | Not yet (Phase 3) |

## Quick start

```bash
cd apps/api
uv sync --extra dev
cp .env.example .env        # optional; defaults work offline
uv run uvicorn app.main:app --reload --port 8000
```

- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/v1/health>
- Scoring weights: <http://localhost:8000/v1/meta>

Everything runs offline with SQLite and local file storage. No API key is
required unless `ATS_API_KEY` is set.

### Tests and checks

```bash
uv run pytest -q          # 42 tests
uv run ruff check app tests
```

## Endpoints

All routes are under `/v1`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + build info |
| GET | `/meta` | Weights, caps, match tiers, model versions |
| POST | `/resumes` | Upload resume (`multipart/form-data`, field `file`) |
| GET | `/resumes` | List resumes |
| GET | `/resumes/{id}` | Canonical JSON, source map, parse issues |
| DELETE | `/resumes/{id}` | Delete resume + stored files |
| GET | `/resumes/{id}/versions` | Version history |
| POST | `/jds` | Submit JD text or URL |
| GET | `/jds/{id}` | JD analysis |
| GET | `/jds` | List JDs |
| POST | `/score` | `{resume_id, jd_id}` → explainable score report |
| GET | `/scores/{id}` | Retrieve a stored score |
| GET | `/resumes/{id}/scores` | Score history |
| POST | `/optimise` | `{resume_id, jd_id, target_score?, options}` → async job |
| GET | `/jobs/{id}` | Job status + proposals |
| GET | `/jobs/{id}/events` | SSE progress stream |
| POST | `/jobs/{id}/changes/{change_id}` | Accept/reject one proposal |
| POST | `/facts` | Add a user-confirmed fact |
| GET | `/facts` | List facts |
| DELETE | `/facts/{id}` | Delete a fact |

### Example flow

```bash
curl -F "file=@resume.pdf" http://localhost:8000/v1/resumes

curl -X POST http://localhost:8000/v1/jds \
  -H "Content-Type: application/json" \
  -d '{"text":"Senior Backend Engineer... 5+ years Python, FastAPI, Kubernetes."}'

curl -X POST http://localhost:8000/v1/score \
  -H "Content-Type: application/json" \
  -d '{"resume_id":"...","jd_id":"..."}'

curl -X POST http://localhost:8000/v1/optimise \
  -H "Content-Type: application/json" \
  -d '{"resume_id":"...","jd_id":"...","options":{"max_iterations":3}}'
```

## How scoring works

Weights are defaults from architecture doc §4.3 and are returned with every
report so results stay explainable.

| Component | Weight | What it measures |
|---|---|---|
| Keyword match | 30% | Exact/alias/lemma match; must-haves count 2× nice-to-haves |
| Semantic relevance | 20% | Bullet-to-requirement similarity |
| Experience fit | 15% | Merged years of experience, seniority, recency, leadership |
| Parseability | 15% | Field recall, headings, contact block, extraction issues |
| Impact | 10% | Action verb, metric, length, weak phrases |
| Education | 5% | Degree level vs stated requirement |
| Readability | 5% | Flesch band, sentence length, tense, passive voice |

Skill matching tiers:

| Match | Credit |
|---|---|
| Exact | 1.00 |
| Alias / synonym | 0.95 |
| Semantic fallback | ≤ 0.60 |
| Skills list only, no bullet evidence | × 0.70 |

Caps and penalties:

- Missing a hard must-have skill → cap at 70
- Parse fidelity below 60 → cap at 60
- Keyword stuffing / hidden text → up to 18-point penalty

The report includes `caps`, `penalties`, per-component detail, and
`recommendations` with priorities. Scores are a **proxy**, not ground truth,
and the API says so in `/meta` and the docs.

## Optimiser guardrails

Change proposals are generated deterministically, then validated by a verifier
that fails closed:

1. No numeric claim that is not in the source or the Facts Bank.
2. No new employer, product, or proper noun.
3. At most two new content tokens, and only if they are action verbs.
4. Skill reordering must preserve the exact skill set.

The optimiser never silently applies changes. Each proposal has
`truthfulness` (`verified` / `needs_user_input`), a risk level, and a rationale.
Missing must-have skills become questions, not inserted claims. The placeholder
pattern is `[ADD METRIC: quantify scale, % improvement, or time saved]`.

## Layout

```
apps/api/
├── app/
│   ├── api/v1/          # routers: resumes, jds, score, jobs, facts
│   ├── core/            # settings, JSON logging, error envelope
│   ├── db/              # SQLAlchemy 2 models + async session
│   ├── schemas/         # Pydantic v2 contracts
│   ├── services/
│   │   ├── ingest/      # pdf, docx, latex, heuristic structurer
│   │   ├── scoring/     # 7 components + engine + embedder
│   │   ├── llm/         # provider interface + versioned prompts
│   │   ├── jd_analyser.py
│   │   ├── optimiser.py
│   │   ├── verifier.py
│   │   └── fetch.py     # SSRF-guarded JD URL fetch
│   ├── storage/         # local storage behind a Protocol
│   └── taxonomy/        # skill aliases + categories
├── alembic/             # initial schema migration
└── tests/               # API, ingest, scoring, verifier tests
```

## Data model

`users`, `resumes`, `resume_versions`, `job_descriptions`, `score_reports`,
`facts_bank`, `bullets`, `jobs`, `audit_log` — matching doc §6.

Embeddings are stored as JSON for portability. The pgvector migration is a
Phase 2 change; the column shape and interface are already in place.

## Configuration

See [`.env.example`](.env.example). Highlights:

- `ATS_DATABASE_URL` — SQLite by default; `postgresql+psycopg://...` for Postgres
- `ATS_AUTO_CREATE_TABLES` — `false` in production, then `alembic upgrade head`
- `ATS_API_KEY` — when set, required as `X-API-Key` (or `?api_key=` for SSE)
- `ATS_ALLOWED_ORIGINS` — comma-separated CORS origins
- `ATS_LLM_PROVIDER` — `stub` (default), `openai`, or `anthropic`

## Docker

```bash
docker compose -f infra/docker-compose.yml up --build
```

This starts Postgres 16 + pgvector, Redis (reserved for Phase 2), and the API
on <http://localhost:8000>. The container runs `alembic upgrade head` before
starting Uvicorn.

## Deliberate deviations from the doc

- **Jobs run in-process** via FastAPI `BackgroundTasks`. The `jobs` table,
  statuses, progress, and SSE stream are the same shape a Celery/Temporal
  worker will use, so swapping the executor does not change the API.
- **Optimiser returns proposals, not patched files.** Phase 1 has no
  sandboxed compiler, so it does not claim to produce a recompiled PDF.
  `score_after_accepted` is a real re-score of the accepted proposal set.
- **PDF extraction is `pypdf`**, with optional PyMuPDF if installed. OCR and
  multi-extractor comparison arrive with the render worker.
- **Semantic scoring uses a deterministic hashed n-gram embedder**, not a
  trained model. Thresholds are recorded in score details so calibration is
  visible rather than implied.
- **Authentication is a single shared API key.** Per-user auth (Clerk/Auth0)
  is Phase 2; the `users` table and ownership checks are already in place.
