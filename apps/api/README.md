# ATS Engine API

FastAPI gateway and Phase 2 LaTeX + AI/NLP engine for the AI ATS resume scorer and optimiser.
The product and system design live in
[`ats-resume-optimizer-architecture.md`](../../ats-resume-optimizer-architecture.md).

## What works today

| Capability | Status |
|---|---|
| Upload PDF / DOCX / `.tex` / `.tex` zip | Implemented |
| Heuristic + optional schema-validated LLM structuring | Implemented (`ATS_LLM_STRUCTURING_ENABLED`) |
| LaTeX static analysis (ATS risks + hostile-input checks) | Implemented |
| JD analysis (must/nice skills, seniority, years, knock-outs) | Implemented |
| Seven-component explainable scoring with caps and penalties | Implemented |
| Optional constrained LLM judge | Implemented (`ATS_LLM_JUDGE_ENABLED`, bounded blend) |
| Hashed + optional trained embeddings (bge/e5/gte) | Implemented (`ATS_EMBEDDING_PROVIDER`) |
| Optional cross-encoder reranker | Implemented (`ATS_RERANKER_ENABLED`) |
| BM25 baseline + typo-tolerant matching + optional spaCy | Implemented (defaults preserve deterministic scores) |
| Runtime taxonomy loader (JSON/CSV/JSONL) | Implemented (`ATS_TAXONOMY_PATHS`) |
| JD analysis cache (memory or Redis) | Implemented |
| Calibration fit + Spearman validation | Implemented; no labelled corpus ships |
| Fairness redaction before scoring | Implemented with audit counts |
| One master resume → multi-JD preview | Implemented (`POST /resumes/{id}/tailor`) |
| Truthfulness-constrained optimisation proposals + accept/reject | Implemented |
| Summary tailoring, bullet reordering, one-page condensing | Implemented in the optimiser |
| Accepted changes → derived resume version + score report | Implemented; validation PDF when the sandboxed compiler is enabled |
| Version detail, field diff, and export (TEX/PDF/DOCX/JSON) | Implemented (`/versions/{id}`, `/diff`, `/export`) |
| Literal source patching (`export?format=tex&mode=source`) | Implemented for single-file `.tex`; no AST |
| Facts Bank | Implemented |
| PostgreSQL + Alembic schema | Implemented |
| Sandboxed LaTeX compile + PDF parse-fidelity comparison | Implemented, opt-in (`ATS_LATEX_COMPILE_ENABLED`); worker image required |
| Zip / `\input` / `\include` resolution | Implemented |
| OCR for scanned PDFs | Optional (`ATS_OCR_ENABLED` + Tesseract + `.[ocr]`) |
| Embedding persistence + search (JSON/pgvector) | Implemented (`POST /search/similar-bullets`) |
| Celery/Temporal worker | Not yet — jobs run in-process |
| PDF/DOCX/TEX export, source patching, diff UI | Not yet (Phase 3) |

See [`pending.md`](../../pending.md) at the repository root for the full,
doc-by-doc gap list.

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
uv run pytest -q          # 126 tests
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
| POST | `/resumes/{id}/tailor` | Preview one resume against multiple JDs |
| POST | `/search/similar-bullets` | Cosine search over stored bullet embeddings |
| GET | `/versions/{id}` | Version metadata + canonical document |
| GET | `/versions/{id}/diff` | Field-level diff against another/previous version |
| GET | `/versions/{id}/export` | Download `tex`/`pdf`/`docx`/`json`; `mode=source` patches literal TEX |
| POST | `/versions/{id}/changes/{change_id}` | Doc-parity alias for accept/reject |
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
│   ├── api/v1/          # routers: resumes, jds, score, jobs, facts, search, tailor
│   ├── core/            # settings, JSON logging, error envelope
│   ├── db/              # SQLAlchemy 2 models + async session
│   ├── schemas/         # Pydantic v2 contracts
│   ├── services/
│   │   ├── ingest/      # pdf, docx, latex, heuristic + LLM structurer
│   │   ├── latex/       # project resolution, sandbox compile client, renderer, source patcher
│   │   ├── export/      # DOCX renderer
│   │   ├── scoring/     # 7 components + engine + embeddings + BM25 + rerank + judge
│   │   ├── llm/         # retrying provider interface + versioned prompts
│   │   ├── jd_analyser.py
│   │   ├── jd_cache.py  # memory/Redis JD cache
│   │   ├── optimiser.py
│   │   ├── tailoring.py # multi-JD preview
│   │   ├── versions.py  # version loading + canonical diff
│   │   ├── versioning.py
│   │   ├── verifier.py
│   │   └── fetch.py     # SSRF-guarded JD URL fetch
│   ├── storage/         # local storage behind a Protocol
│   └── taxonomy/        # curated aliases + external JSON/CSV loader
├── alembic/             # schema + P0 integrity + optional pgvector migrations
└── tests/               # API, ingest, scoring, LLM, cache, calibration tests
```

## Data model

`users`, `resumes`, `resume_versions`, `job_descriptions`, `score_reports`,
`facts_bank`, `bullets`, `jobs`, `audit_log` — matching doc §6.

Embeddings are stored as JSON for portability and persisted for JDs and resume-version
bullets. `ATS_EMBEDDING_STORE_BACKEND=pgvector` uses the Postgres-only migration
`7a3d9f2c1e44_phase2_embeddings.py` to add native `vector` columns and ivfflat indexes;
search falls back to JSON cosine when pgvector is unavailable.

## Configuration

See [`.env.example`](.env.example). Highlights:

- `ATS_DATABASE_URL` — SQLite by default; `postgresql+psycopg://...` for Postgres
- `ATS_AUTO_CREATE_TABLES` — `false` in production, then `alembic upgrade head`
- `ATS_API_KEY` — when set, required as `X-API-Key` (or `?api_key=` for SSE)
- `ATS_ALLOWED_ORIGINS` — comma-separated CORS origins
- `ATS_LLM_PROVIDER` — `stub` (default), `openai`, or `anthropic`
- `ATS_LLM_STRUCTURING_ENABLED` / `ATS_LLM_JUDGE_ENABLED` — opt-in schema-validated
  structuring and bounded judge
- `ATS_LLM_MAX_RETRIES`, `ATS_LLM_RETRY_BACKOFF_SECONDS`,
  `ATS_LLM_INPUT_COST_PER_MILLION`, `ATS_LLM_OUTPUT_COST_PER_MILLION` — provider
  resilience and cost accounting
- `ATS_EMBEDDING_PROVIDER` — `hashed` (default) or `sentence-transformers`
- `ATS_EMBEDDING_STORE_BACKEND` — `json` (default) or `pgvector` on PostgreSQL
- `ATS_EMBEDDING_VECTOR_DIM` — dimension for the Postgres `vector` column (set before
  the migration; 512 matches the default hashed embedder, 384 fits bge-small)
- `ATS_RERANKER_ENABLED`, `ATS_BM25_WEIGHT`, `ATS_FUZZY_MATCHING_ENABLED`,
  `ATS_SPACY_ENABLED` — optional NLP quality controls
- `ATS_TAXONOMY_PATHS` — comma-separated JSON/CSV/JSONL taxonomy files
- `ATS_JD_CACHE_BACKEND` / `ATS_REDIS_URL` — `memory` (default) or `redis`
- `ATS_CALIBRATION_ENABLED` / `ATS_CALIBRATION_PATH` — frozen logistic calibration
- `ATS_FAIRNESS_REDACTION_ENABLED` — anonymise the scoring view (default on)
- `ATS_LATEX_COMPILE_ENABLED` — `false` by default; enables the sandboxed compiler
- `ATS_LATEX_COMPILE_ENGINE` — `auto` (HTTP worker → Docker → local), `docker`, or `local`
- `ATS_LATEX_WORKER_URL` — long-lived worker URL, e.g. `http://localhost:8099`
- `ATS_LATEX_WORKER_IMAGE` — image used for the one-shot Docker fallback
- `ATS_OCR_ENABLED` — enables the optional Tesseract fallback

### AI/NLP pipeline

The deterministic hashed embedder and heuristic structurer remain the default, so the
offline test suite is reproducible. The optional track adds:

- schema-validated LLM structuring with Pydantic fallback;
- trained embeddings / cross-encoder reranking behind lazy optional imports;
- BM25, typo-tolerant matching, and optional spaCy lemmatisation;
- runtime taxonomy loading, Redis/memory JD caching, calibration utilities;
- fairness redaction with per-report redaction counts;
- a version manifest (`scoring-v2`) covering every model/prompt that affected a score.

### LaTeX pipeline

When compilation is enabled, ingestion resolves zip includes, statically rejects
unsafe constructs, compiles the project in the sandboxed worker, and extracts the
compiled PDF with every available extractor. The PDF text is authoritative for
structuring; extractor agreement and layout flags are stored in
`ResumeDocument.parse_fidelity`. The optimiser and change acceptance compile the
canonical ATS-safe render and roll back on a real compile failure. If no worker or
engine is available, ingestion records `compile_status: unavailable` and continues
with static analysis instead of rejecting the upload.

### Versions and exports

Every accepted/rejected decision writes an immutable canonical-JSON snapshot. `GET
/v1/versions/{id}` returns that snapshot, `/diff` compares it field-by-field with a
previous version, and `/export` streams TEX, DOCX, JSON, or (when the sandbox compiler
is enabled) PDF. `format=tex&mode=source` applies accepted before/after edits to a
literal single-file `.tex` source; unmatched edits are counted in `X-Patch-Skipped`.

## Docker

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

This starts Postgres 16 + pgvector, Redis (optional JD cache), the sandboxed
LaTeX worker, the API on <http://localhost:8000>, and the Next.js UI on
<http://localhost:3000>. The API container runs `alembic upgrade head` before
starting Uvicorn, and the UI starts only after the API health check passes.
Compilation stays disabled unless you set `ATS_LATEX_COMPILE_ENABLED=true`. See the
root [`README.md`](../../README.md) for logs, stop, reset, and optional API-key
commands.

## Deliberate deviations from the doc

- **Jobs run in-process** via FastAPI `BackgroundTasks`. The `jobs` table,
  statuses, progress, and SSE stream are the same shape a Celery/Temporal
  worker will use, so swapping the executor does not change the API.
- **Optimiser returns proposals, not patched files by default.** The optimiser edits
  canonical JSON and validates the canonical ATS-safe render through the sandboxed
  compiler. Accepted changes can be exported as canonical TEX/DOCX/PDF/JSON, and literal
  single-file TEX sources can be patched with `mode=source`. `score_after_accepted` is a
  real re-score of the accepted proposal set.
- **PDF extraction uses `pypdf` plus optional PyMuPDF and `pdftotext`.** The API Docker
  image installs the `pdf` extra and `poppler-utils`, so all three run in production.
  Extractor agreement is reported rather than treated as ground truth. The compiled PDF
  is authoritative only when compilation is enabled and succeeds.
- **Apache Tika and full reading-order reconstruction are not implemented.** Layout
  detection relies on PyMuPDF block geometry.
- **The LaTeX worker is a separate image.** The API image stays small; the worker
  carries TeX Live, runs read-only with limits, and is attached to an internal-only
  network in Compose.
- **PDF export depends on the sandboxed compiler.** Without it, `/export?format=pdf`
  returns a clear `pdf_export_unavailable` 409; TEX/DOCX/JSON always work.
- **Source patching is literal text replacement, not AST editing.** It works for common
  literal templates but cannot reflow arbitrary macros or zip projects.
- **Semantic scoring uses a deterministic hashed n-gram embedder by default.** Trained
  bge/e5/gte embeddings and a cross-encoder reranker are opt-in; thresholds and the
  active model are recorded in score details and the version manifest.
- **LLM features are opt-in and fail closed.** Structuring validates with Pydantic and
  falls back to the heuristic result; the judge is clamped and blended only within the
  deterministic cap; providers retry with bounded backoff and record cost/usage.
- **Fairness redaction is signal removal, not a statistical audit.** Scoring uses an
  anonymised view and reports redaction counts; labelled demographic outcomes are needed
  for a true group-fairness study.
- **Authentication is a single shared key or per-user API keys.** SSO (Clerk/Auth0),
  plans, and billing remain future work; the `users` table and ownership checks are in
  place.
