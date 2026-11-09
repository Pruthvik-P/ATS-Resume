# Pending Work — AI ATS Resume Optimiser

Audit date: **2026-11-09**
Source of truth: [`ats-resume-optimizer-architecture.md`](ats-resume-optimizer-architecture.md)
Current phase: **Phase 1 + Phase 2 LaTeX and AI/NLP tracks implemented (opt-in)**

Verification at audit time:

- `cd apps/api && uv run pytest -q` → **117 passed**
- `cd apps/api && uv run ruff check app tests` → **clean**
- `cd apps/web && npm run lint` → **clean**
- `cd apps/web && npx tsc --noEmit` → **clean**
- `docker compose -f infra/docker-compose.yml config` → **valid**
- `cd apps/api && uv run alembic upgrade head` → **clean on SQLite** (the pgvector DDL is
  PostgreSQL-only and no-ops elsewhere)
- `docker build -t ats-latex-worker:latest services/latex_worker` → **built**
- Real compile + PDF extraction verified through both worker transports (one-shot
  `docker run --network none` and HTTP `/compile`).
- pgvector migration, JD/bullet embedding writes, and `<=>` cosine search verified
  against a live `pgvector/pgvector:pg16` container.
- Docker Compose stack (Postgres + Redis + API + Next.js web + LaTeX worker) is defined and documented.
- **Caveat:** the host has no local TeX engine, `pdftotext`, or Tesseract. The Docker
  worker/API images supply TeX Live, PyMuPDF, and `pdftotext`; OCR remains untested here
  because Tesseract is not in the default image. Trained embedding/reranker models were
  not downloaded on this host.

Legend: `[ ]` pending · `[~]` partially implemented · `[x]` done in this pass

---

## 0. Completed in this audit pass

- [x] Accepted changes now persist as a derived `ResumeVersion`, bump `resumes.version`,
      store the updated canonical resume, and write/update a `score_reports` row linked
      to that version (`apps/api/app/api/v1/jobs.py`).
- [x] `/v1/score` now records `resume_version_id` and links the latest version's
      `score_id` (`apps/api/app/api/v1/score.py`).
- [x] Added regression assertions for version/score persistence after a change decision
      (`apps/api/tests/test_jobs.py`).
- [x] Updated API/root READMEs and added this file.

The changes are metadata-level plus immutable canonical-JSON snapshots. When
`ATS_LATEX_COMPILE_ENABLED` is on and a worker is available, accepted versions also
store a validation PDF (`pdf_url`); the original user `.tex` files are still not
patched in place.

---

## 1. P0 — Truthfulness, approvals, and data integrity

- [x] **Editable proposal text.** Added `PATCH /v1/jobs/{job_id}/changes/{change_id}`
      and an optional `proposed` field on decision requests. Edits are verified,
      flagged `edited_by_user`, and applied by `target_ref` rather than string matching
      (`apps/api/app/api/v1/jobs.py`, `apps/api/app/services/optimiser.py`). The web
      proposal card now exposes an inline editor (`apps/web/src/components/proposal-card.tsx`).
- [x] **Metric placeholder workflow.** `placeholder_metric` proposals keep the full
      source bullet, require the user to replace `[ADD METRIC: …]`, re-run verification
      on save, and refuse acceptance while the placeholder remains. Verified user edits
      are recorded in the Facts Bank before the change can be accepted.
- [x] **Reject-after-accept semantics.** Decisions are applied to the job’s base
      document (the parent version snapshot), so rejecting an accepted change restores
      the original content. Every decision appends a `change_decision` event (including
      `previous_status` and `reverted`) to an append-only change log, and reverted
      content remains addressable because each decision writes a new revision snapshot.
- [x] **Version file provenance.** Each upload and each decision writes an immutable
      JSON snapshot under
      `resumes/{resume_id}/versions/{version_id}/…` and stores it in
      `snapshot_url`; derived versions inherit the source `tex_url`. When the sandboxed
      compiler is enabled, a validation PDF is also written and exposed as `pdf_url`.
      Migration: `9c1f2e7a4b6d_p0_integrity.py`.
- [x] **True one-click delete / retention.** Added `DELETE /v1/account` (delete all
      user data) and `POST /v1/account/purge` (apply `ATS_RETENTION_DAYS` or an explicit
      window). Deletion is explicit and ordered leaf-to-root, so it cleans versions,
      scores, facts, jobs, JDs, audit rows, and stored objects on SQLite as well as
      Postgres (`apps/api/app/services/retention.py`, `apps/api/app/api/v1/account.py`).
- [x] **Per-user ownership and auth.** `ATS_API_KEYS="email=key,…"` now maps each key
      to its own `users` row, so resumes/JDs/jobs/facts are isolated per key. The shared
      `ATS_API_KEY` and open local mode remain for dev. **Caveat:** this is an API-key
      ownership boundary, not SSO; Clerk/Auth0/Supabase/Keycloak, plan enforcement, and
      billing still need a real identity provider.
- [x] **Rate limiting / abuse protection.** Added a sliding-window limiter with
      request, upload, and optimise-job limits (`ATS_RATE_LIMIT_REQUESTS_PER_MINUTE`,
      `ATS_RATE_LIMIT_UPLOADS_PER_MINUTE`,
      `ATS_RATE_LIMIT_OPTIMISE_JOBS_PER_HOUR`). **Caveat:** it is in-process memory, so
      a multi-worker or multi-replica deployment still needs Redis or gateway limiting.
- [x] **Idempotency and concurrent decisions.** `POST /v1/optimise` accepts
      `Idempotency-Key` with a unique `(user_id, idempotency_key)` index and
      replay/conflict handling. Decisions load the job with `SELECT … FOR UPDATE`,
      serialize concurrent writes, and short-circuit exact replays with
      `idempotent_replay: true` (`apps/api/app/api/v1/jobs.py`).

---

## 2. Phase 2 — LaTeX engine and parse fidelity (the main differentiator)

- [x] **Sandboxed LaTeX render worker.** Added `services/latex_worker` (stdlib HTTP
      worker + one-shot stdin/stdout mode) and a Debian TeX Live + `latexmk` image.
      Compose runs it read-only, non-root, with `no-new-privileges`, all capabilities
      dropped, memory/CPU/PID limits, and a tmpfs `/tmp`. The HTTP path is attached to
      an `internal: true` network; the Docker one-shot path uses `--network none`.
      Static rejection and `shell_escape=f` / `openin_any=p` / `openout_any=p` are
      enforced. **Caveat:** there is no TeX package allow-list because TeX Live ships
      a large package set; the security boundary is the sandbox, not the package list.
      The reference image targets pdfLaTeX/`latexmk`; XeLaTeX/LuaLaTeX-only templates
      (`fontspec`) need an engine-selection extension.
- [x] **Compile `.tex` → PDF.** `apps/api/app/services/latex/compiler.py` selects an
      HTTP worker, then a one-shot Docker container, then a local
      Tectonic/`latexmk`/`pdflatex` fallback in `local`/`test`. Compilation is opt-in
      (`ATS_LATEX_COMPILE_ENABLED`). The compiled PDF is the authoritative ingestion
      text and is saved with accepted derived versions (`pdf_url`). The Docker worker
      was verified end-to-end through both the one-shot and HTTP transports; an
      unavailable worker degrades to static analysis instead of failing the upload.
      **Caveat:** the local Tectonic/`latexmk` fallback was not exercised on this host.
- [x] **Multi-extractor parse-fidelity comparison.** `extract_pdf` compares `pypdf`,
      optional PyMuPDF, and optional `pdftotext` output by token agreement. Agreement
      and disagreements are stored in `ResumeDocument.parse_fidelity` and surfaced in
      the parseability details. **Caveat:** Apache Tika is not implemented.
- [~] **Reading-order / column / table detection on the compiled PDF.** PyMuPDF block
      geometry detects side-by-side columns, tall sidebar blocks, and tables when
      PyMuPDF is installed. Blocks are measured in memory. Full reading-order
      reconstruction is not implemented.
- [~] **SyncTeX mapping.** The worker returns `main.synctex.gz` and `CompileResult`
      keeps it, but no PDF position → `.tex` line mapping is consumed yet.
- [ ] **LaTeX AST editing.** Still no `pylatexenc` / `TexSoup` / Pandoc AST. The
      optimiser edits canonical JSON and the canonical ATS-safe renderer; it does not
      patch macro-safe text nodes in the user's original template.
- [x] **`\input` / `\include` / zip resolution.** `apps/api/app/services/latex/project.py`
      loads single `.tex` files and zips, detects the main file, validates entries, and
      recursively expands `\input`/`\include`/`\subfile` with cycle/depth/size checks.
- [x] **Macro registry expansion.** `_TEXT_MACROS` now covers Jake's Resume, AltaCV,
      moderncv-style, and common custom macros; dynamic structural-macro matching keeps
      argument groups. Unknown macros fall back to compile-and-extract. **Caveat:**
      arbitrary user macros still depend on the compiler/fallback path.
- [~] **ATS-safe preamble auto-fix.** `apply_preamble_fixes` adds T1 `fontenc`,
      `glyphtounicode`, and `pdfgentounicode` once and is unit-tested. The canonical
      renderer always emits them. It is not automatically written back into the user's
      original uploaded file.
- [~] **OCR fallback.** `ATS_OCR_ENABLED` plus the optional `ocr` extra
      (`pymupdf`, `pytesseract`, `pillow`) can OCR low-text PDFs. **Caveat:** Tesseract
      is not installed in this environment or the default Docker image, so the path is
      opt-in and unverified here.
- [~] **PDF layout extraction.** `PdfExtraction.blocks` records page/bbox/text blocks
      and layout flags summarize multi-column, sidebar, and table risks. Bounding boxes
      are not persisted per resume and reading order is not reconstructed.
- [x] **DOCX table/text-box fidelity.** `extract_docx` walks tables in document order,
      detects nested tables, text boxes, and header/footer text, and emits specific
      warnings. **Caveat:** there is no rendered/round-trip comparison yet.
- [x] **Compile rollback.** The optimiser validates each iteration with the sandboxed
      compiler and rolls back the whole iteration on `failed`/`timeout`/`rejected`.
      Change acceptance also validates the full updated document and returns a 409 on a
      real compile failure; unavailable workers do not block acceptance.

---

## 3. Phase 2 — AI, NLP, taxonomy, and scoring quality

- [x] **LLM structuring.** Added `app/services/ingest/llm_structurer.py` with a
      schema-constrained prompt, Pydantic validation, field-level merging over the
      heuristic result, and explicit fallback issues. Enabled by
      `ATS_LLM_STRUCTURING_ENABLED`; the default heuristic path is unchanged.
      **Caveat:** schema validation is not a factual verifier, so LLM structuring
      remains opt-in and the deterministic heuristic is the safe default.
- [x] **LLM provider hardening.** `app/services/llm/base.py` now returns an
      `LLMResult` with provider/model/prompt-version attribution, retries with
      exponential backoff, timeout, JSON extraction, token usage, cost estimates,
      attempt/latency tracing, and provider-specific response parsing. Callers still
      validate the returned object with Pydantic.
- [x] **Constrained LLM judge for scoring.** `app/services/scoring/judge.py` asks for a
      schema-shaped verdict, clamps the advisory score/adjustment/confidence, records
      strengths/gaps/rationale, provider/model, prompt version, and usage. Enabled by
      `ATS_LLM_JUDGE_ENABLED`; `ATS_LLM_JUDGE_BLEND_WEIGHT` controls the bounded blend
      (default `0`, so the deterministic score is unchanged). The cap ceiling is honored.
- [x] **Trained embeddings.** `app/services/scoring/embedding.py` now has a provider
      interface with the deterministic `HashedEmbedder` default and an optional
      `SentenceTransformerEmbedder` (bge/e5/gte). A missing model falls back to hashed
      and records the requested model. Per-model calibration bands and a bounded text
      cache are included. Enable with `ATS_EMBEDDING_PROVIDER=sentence-transformers`.
- [x] **Cross-encoder reranker.** Added `app/services/scoring/rerank.py` with an
      optional `bge-reranker` cross-encoder. `ATS_RERANKER_ENABLED` enables it and
      `ATS_RERANKER_WEIGHT` blends top embedding candidates with reranker scores.
      Load failures disable it rather than failing scoring; default is off.
- [x] **BM25 / TF-IDF baseline.** Added a pure-Python `BM25` implementation
      (`apps/api/app/services/scoring/bm25.py`) and a configurable
      `ATS_BM25_WEIGHT` blend into semantic matching. The default weight is `0` so the
      existing deterministic scores are unchanged.
- [x] **spaCy / rapidfuzz.** Added typo-tolerant phrase matching with `rapidfuzz` when
      installed and a `difflib` fallback, plus optional spaCy lemmatisation via
      `ATS_SPACY_ENABLED`. Skill matching records `fuzzy_fallback` evidence; the
      deterministic stemmer remains the default.
- [~] **Full skills taxonomy.** Added `app/taxonomy/loader.py` for JSON/CSV/JSONL
      imports with ESCO/O*NET/Lightcast-style column mapping, plus runtime merges
      (`ATS_TAXONOMY_PATHS`) and a content-hash `taxonomy_version`. The curated alias
      table remains the shipped data; the full external datasets and a dedicated
      skill-NER are not bundled. **Caveat:** taxonomy quality depends on the operator
      supplying a licensed export.
- [x] **pgvector / embedding storage.** `app/services/scoring/embedding_store.py` persists
      JD embeddings and version bullet embeddings, and `/v1/search/similar-bullets`
      exposes cosine search. JSON storage works on SQLite; the Postgres-only migration
      `7a3d9f2c1e44_phase2_embeddings.py` adds native `vector(ATS_EMBEDDING_VECTOR_DIM)`
      columns + ivfflat indexes, and the service uses `<=>` when
      `ATS_EMBEDDING_STORE_BACKEND=pgvector`. The migration, writes, and distance search
      were verified against a live `pgvector/pgvector:pg16` container; any pgvector
      failure falls back to JSON cosine. **Caveat:** this live Postgres path is not yet
      in CI.
- [x] **JD analysis cache.** Added `app/services/jd_cache.py` with a bounded TTL/LRU
      in-process cache keyed by analyser version + text/title/company, plus optional
      Redis JSON caching when `ATS_JD_CACHE_BACKEND=redis` and `ATS_REDIS_URL` are set.
      Redis failures fall back to memory. Embedding text caching is also bounded.
- [x] **Calibration.** Added `app/services/scoring/calibration.py` with a pure-Python
      logistic-regression fit, frozen JSON models, Spearman validation, and an optional
      bounded blend (`ATS_CALIBRATION_ENABLED`, `ATS_CALIBRATION_PATH`,
      `ATS_CALIBRATION_BLEND_WEIGHT`). The default is disabled/identity, so existing
      deterministic scores are unchanged. **Caveat:** labelled outcome data is still an
      operator input; no corpus ships with the repo.
- [x] **Fairness controls.** Added `app/services/scoring/fairness.py`: the scoring view
      removes name, contact details, location, profiles/photos, gender pronouns, age,
      nationality/status labels, marital status, and postal addresses before
      keyword/semantic/impact/readability scoring. Parseability still uses the original
      document so legitimate ATS field extraction is not penalised. Report-level
      redaction counts are stored in `ScoreReport.fairness`; `ATS_FAIRNESS_REDACTION_ENABLED`
      toggles it. **Caveat:** this is signal removal + transparency, not a statistical
      group-fairness audit (no labelled demographic outcomes).
- [x] **Model/prompt version reproducibility.** Added
      `app/services/versioning.py` and `scoring-v2` manifests recorded in every
      `ScoreReport.model_versions` and optimiser result: scoring engine, embedding,
      reranker, taxonomy hash, structuring model/prompt, JD analyser, LLM
      provider/model, rewriter prompt, fairness mode, calibration, and BM25/reranker
      weights. `ScoreReport.scoring_version` is set explicitly.
- [~] **Multi-JD tailoring.** Added `POST /v1/resumes/{id}/tailor` with
      `app/services/tailoring.py`: one master resume is scored and optimised against up
      to `ATS_MULTI_JD_MAX_TARGETS` JDs, returning a comparison of baseline/proposed
      scores and top verified proposals. **Caveat:** this is a preview; it does not
      persist per-JD versions (use an optimise job + approvals for that).

---

## 4. Phase 3 — Optimiser loop, versions, and export

- [ ] **Compile → re-score → keep-or-rollback loop.** `run_optimisation` re-scores the
      canonical document in memory, but never compiles, lints, or compares PDF parse
      fidelity after each patch.
- [ ] **Summary tailoring.** `summary_tailor` exists as a proposal kind but is never
      generated. The summary is not rewritten for the JD.
- [ ] **Bullet/section reordering by relevance.** Only skill-group/keyword reordering is
      implemented.
- [ ] **One-page condensing.** No token-aware condensing or page-count logic.
- [ ] **Broader bullet rewriting.** Deterministic rewriting only replaces a fixed list of
      weak prefixes; it does not perform task → action → result restructuring.
- [ ] **Export endpoint.** Doc §7 lists
      `GET /v1/versions/{id}/export?format=pdf|tex|docx`; it is absent.
- [ ] **PDF export.** No compiled PDF output.
- [ ] **DOCX export.** `python-docx` reads DOCX but does not write it.
- [ ] **TEX export / patched source.** Original `.tex` bytes are stored, but no optimised
      `.tex` file is produced or downloadable.
- [ ] **Version detail and diff API.** `GET /v1/resumes/{id}/versions` returns metadata
      only. There is no `GET /v1/versions/{id}` with canonical/source content, and no
      before/after diff endpoint.
- [ ] **Doc endpoint parity.** Doc §7 uses
      `POST /v1/versions/{id}/changes/{change_id}/accept`; the implementation is
      `POST /v1/jobs/{id}/changes/{change_id}`. Either add aliases or record the deviation
      permanently.
- [ ] **Change log before/after text.** Version change logs store status/target/rationale,
      not the full before/after strings required for a reviewer-facing change log.
- [ ] **Facts Bank feeding the optimiser in UI flow.** The API reads facts for LLM
      planning, but the web flow offers no way to add/confirm facts, so missing-skill
      questions cannot be answered in-product.
- [ ] **Template support for AST patching.** Doc Phase 3 targets 2–3 popular templates; none
      are supported because there is no AST/compiler.

---

## 5. Frontend (`apps/web`)

- [ ] **JD URL input.** Backend `/v1/jds` supports `url` with an SSRF guard; the UI only
      accepts pasted text and labels the mode “paste text”
      (`apps/web/src/components/upload-form.tsx`). Doc §3 calls for paste/URL.
- [ ] **Facts Bank UI.** No page/panel to list, add, confirm, or delete facts.
- [ ] **Version history UI.** No view of resume versions, score history, or change logs.
- [ ] **Export/download UI.** No PDF/TEX/DOCX download button.
- [x] **Proposal editor.** Inline editor for bullet rewrites and
      `[ADD METRIC: …]` placeholders, with save-and-verify, live placeholder
      validation, and an "edited by you" provenance badge
      (`apps/web/src/components/proposal-card.tsx`).
- [ ] **Monaco LaTeX editor.** Not installed/used (doc §5 recommends
      `@monaco-editor/react`).
- [ ] **Live PDF preview.** No `react-pdf` / PDF.js preview.
- [ ] **Diff viewer.** Proposal cards show two text panes, but there is no proper
      word-level diff (`react-diff-viewer` or equivalent).
- [ ] **Upload flow for `.zip` content.** UI accepts `.zip`, but multi-file LaTeX
      projects are not resolvable; preview/editor would be needed for real projects.
- [~] **PII / privacy controls.** Backend now has delete-all (`DELETE /v1/account`)
      and retention purge (`POST /v1/account/purge`); the web UI does not expose those
      controls yet, and there is still no redaction/Presidio pass.
- [ ] **Frontend tests.** No unit tests, component tests, Playwright/Cypress E2E, or
      accessibility test suite.
- [ ] **Error coverage.** Some error hints are unreachable (for example
      `jd_url_blocked`) because the corresponding UI affordance does not exist.

---

## 6. Infrastructure, security, and operations

- [x] **Sandbox worker service.** `infra/docker-compose.yml` now builds
      `services/latex_worker` and attaches it to an internal network. Redis is now
      optionally used by the JD analysis cache.
- [ ] **Queue/worker execution.** Jobs run via FastAPI `BackgroundTasks`
      (`apps/api/app/api/v1/jobs.py`). No Celery/Temporal/RQ/Dramatiq, no durable retries,
      no dead-letter handling, no cross-process progress.
- [~] **Resource limits.** The LaTeX worker has container CPU/memory/PID/time/output
      limits and a wall-clock timeout. General optimisation jobs still rely on the SSE
      300-second stream timeout and a stale-job setting.
- [ ] **S3/MinIO storage.** `storage_backend` is local-only; S3/MinIO/R2 support is absent.
- [~] **Postgres in production path is only partially exercised.** Docker installs
      `.[postgres,pdf,nlp,redis]`; local default is SQLite. The pgvector migration and
      cosine search were manually verified against `pgvector/pgvector:pg16`, but no
      Postgres-specific CI matrix runs yet.
- [~] **Optional extras missing from the image.** Docker installs
      `.[postgres,pdf,nlp,redis]` plus `poppler-utils`. The large `embeddings`/`spacy`
      extras and the OCR stack (`ocr` extra + Tesseract) are not installed; the LaTeX
      worker is a separate image.
- [ ] **Observability.** No OpenTelemetry tracing, Prometheus metrics, Sentry, Langfuse
      LLM tracing, or dashboarding. Current logging is structured app logging only.
- [ ] **CI/CD.** No `.github/workflows`; no lint/test/build pipeline; no image publishing;
      no dependency or secret scanning.
- [ ] **Terraform / Kubernetes.** No IaC or K8s manifests; only a single Compose file.
- [ ] **TLS and encryption at rest.** No TLS termination, S3 SSE, or Postgres encryption
      configuration. PII is stored as plain local files/rows in the default setup.
- [~] **PII redaction.** Scoring now uses an anonymised fairness view (name, contact,
      location, profiles, protected-attribute phrases), but Microsoft Presidio is not
      installed and resumes are still sent to external LLM providers without a dedicated
      redaction pass.
- [ ] **Zero-retention provider controls.** No provider selection or policy enforcement for
      no-training/zero-retention terms; no self-hosted open-weight model path (vLLM/Ollama).
- [ ] **Audit log access.** `audit_log` rows are written by many endpoints but there is no
      read API, export, or UI.
- [ ] **Secret hygiene.** `.env.example` documents keys, but there is no secret manager or
      startup validation for production (for example, refusing `ATS_API_KEY=""`).
- [~] **Security tests.** Hostile LaTeX, traversal/corrupt-zip, and worker-protocol tests
      exist. No fuzzing, zip-bomb matrix, SSRF resolution matrix, or dedicated sandbox
      escape suite yet.
- [ ] **Type checking in CI.** `mypy` is not clean: it reports pre-existing errors in
      `apps/api/app/services/scoring/semantic.py` and
      `apps/api/app/services/ingest/pipeline.py`. `ruff` and `pytest` pass.

---

## 7. Data, evaluation, and calibration

- [ ] **Resume corpus.** No consented/synthetic/public resume corpus, and no 20+ LaTeX
      template corpus.
- [ ] **JD corpus.** No role/seniority-stratified job-description corpus.
- [~] **Labelled outcomes.** A calibration fit/Spearman utility exists, but no
      shortlisted/rejected labels or consented demographic outcomes ship with the repo, so
      production calibration and group-fairness measurement cannot be run yet.
- [ ] **Golden parsing set.** No field-level F1 benchmark for name/title/date/skill
      extraction.
- [ ] **Golden hallucination set.** No automated zero-hallucination suite or
      `promptfoo`/Ragas/DeepEval configuration.
- [ ] **Regression evals in CI.** No eval runner gated on prompt/model changes.
- [ ] **Performance benchmarks.** No end-to-end latency targets/measurements for score
      (< 15 s) or optimise (< 90 s), and no load tests.
- [ ] **Score stability test.** No repeat-run ±2-point stability check.
- [ ] **Competitor/parser benchmarks.** No comparison against Affinda, Textkernel,
      RChilli, or other commercial parsers (doc §8 reference list).

---

## 8. Repository layout vs. doc §12

Doc §12 proposes `apps/web`, `apps/api`, `services/*`, `packages/*`, `evals/`, `infra/`,
`docs/`. Current reality:

- [x] `apps/web`, `apps/api`, `infra/`
- [ ] `services/ingest`, `services/jd_analyser`, `services/scoring`,
      `services/optimiser` (currently inside `apps/api/app/services`)
- [x] `services/latex_worker` (container worker)
- [ ] `packages/schemas`, `packages/taxonomy`, `packages/latex_templates`
- [ ] `evals/` golden sets and promptfoo configs
- [ ] `docs/`

This is a deliberate MVP monolith; list it as a known deviation until extraction is worth
the operational cost.

---

## 9. Doc-vs-code deviations to keep or close

| Doc expectation | Current implementation | Action |
|---|---|---|
| Celery/Redis or Temporal queue | `BackgroundTasks`; Redis used only for optional JD cache | Add a durable queue in Phase 3 |
| pgvector in Postgres | JSON vectors everywhere + native pgvector columns/search (live-verified) | Add a CI Postgres matrix |
| Multi-extractor parse fidelity | pypdf + optional PyMuPDF/`pdftotext` with token agreement | Tika remains optional |
| Sandboxed LaTeX compile | Worker + Docker/local fallback, opt-in; compile rollback | Tune limits with real workloads |
| LLM structuring + `instructor` | Heuristic default + optional schema-validated LLM structuring | Add provider evals |
| LLM judge in score | Optional bounded LLM judge with clamped adjustment | Decide production blend |
| Trained embeddings + reranker | Optional sentence-transformers/CrossEncoder behind fallbacks | Benchmark on a labelled set |
| Monaco + PDF preview + diff viewer | Plain React panels | Close in Phase 3 |
| `/v1/versions/{id}/export` | Not present | Close in Phase 3 |
| `/v1/versions/{id}/changes/.../accept` | `/v1/jobs/{id}/changes/...` | Alias or document |
| Per-user auth (Clerk/Auth0) | Per-user API keys via `ATS_API_KEYS`; no SSO/plans | Close before multi-user |
| S3/MinIO storage | Local filesystem only | Close before hosted deployment |
| Presidio PII redaction | Fairness scoring view; no Presidio pass before external LLM calls | Close before external LLM use |

---

## 10. Suggested next sprint (ordered)

1. ~~**Editable proposal + metric workflow.**~~ Done in the P0 pass: `PATCH
   /v1/jobs/{id}/changes/{change_id}`, verifier re-run, Facts Bank recording, and the
   inline web editor. Next: expose the Facts Bank and version/export UI.
2. **Facts Bank + version/export UI.** Expose the existing facts, versions, search, and
   multi-JD preview APIs; show a change log; add at least TEX/JSON export.
3. **JD URL input.** Reuse the existing SSRF-guarded `/v1/jds` URL path in the UI.
4. ~~**LaTeX worker spike.**~~ Done: sandboxed worker, one-shot/HTTP transports,
   multi-extractor PDF comparison, and compile rollback. Next: run Jake’s/AltCV/moderncv
   template fixtures in CI.
5. ~~**Trained embeddings + pgvector.**~~ Implemented behind opt-in providers and a
   Postgres-only migration. Next: benchmark bge/e5 + reranker on a labelled set and run
   the pgvector path against a live Postgres service.
6. **Golden set + CI.** Start with 20–50 resume/JD pairs, field-F1 parsing checks,
   hallucination checks, and a GitHub Actions pipeline.
7. **LLM quality/evals.** Add promptfoo/Ragas/DeepEval runs, cost budgets, and a
   constrained judge evaluation before enabling LLM structuring or blending in production.
8. **Durable jobs + observability.** Add a queue/worker, OpenTelemetry/metrics, and
   Postgres/pgvector integration tests.
