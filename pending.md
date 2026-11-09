# Pending Work — AI ATS Resume Optimiser

Audit date: **2026-11-09**
Source of truth: [`ats-resume-optimizer-architecture.md`](ats-resume-optimizer-architecture.md)
Current phase: **Phase 1 implemented; Phase 2 LaTeX/parse pipeline implemented (opt-in)**

Verification at audit time:

- `cd apps/api && uv run pytest -q` → **79 passed**
- `cd apps/api && uv run ruff check app tests` → **clean**
- `cd apps/web && npm run lint` → **clean**
- `cd apps/web && npx tsc --noEmit` → **clean**
- `docker compose -f infra/docker-compose.yml config` → **valid**
- `docker build -t ats-latex-worker:latest services/latex_worker` → **built**
- Real compile + PDF extraction verified through both worker transports (one-shot
  `docker run --network none` and HTTP `/compile`).
- Docker Compose stack (Postgres + API + Next.js web + LaTeX worker) is defined and documented.
- **Caveat:** the host has no local TeX engine, `pdftotext`, or Tesseract. The Docker
  worker/API images supply TeX Live, PyMuPDF, and `pdftotext`; OCR remains untested here
  because Tesseract is not in the default image.

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

- [ ] **LLM structuring.** `StructuringMeta.method` supports `llm`, but the only code path
      is `deterministic-heuristic-v1` in `apps/api/app/services/ingest/structurer.py`.
      No schema-constrained extraction (`instructor` / JSON-schema mode) exists.
- [ ] **LLM provider hardening.** Providers are raw `httpx` calls
      (`apps/api/app/services/llm/base.py`): no retries, timeouts are basic, no token/cost
      accounting, no provider SDK, no schema enforcement, no prompt/response tracing.
- [ ] **Constrained LLM judge for scoring.** The doc calls for an optional LLM judge in the
      hybrid score; scoring is deterministic rules only.
- [ ] **Trained embeddings.** Semantic scoring uses `HashedEmbedder`
      (`hashed-ngram-v1`), not bge/e5/gte via `sentence-transformers`.
- [ ] **Cross-encoder reranker.** No `bge-reranker` / Cohere Rerank; bullet-to-requirement
      matching is pure embedding/lexical similarity.
- [ ] **BM25 / TF-IDF baseline.** `rank_bm25` and scikit-learn are not implemented, despite
      being in the doc’s scoring stack.
- [ ] **spaCy / rapidfuzz.** Not installed or used; lemmatisation and typo-tolerant matching
      rely on custom tokenisation (`apps/api/app/services/text.py`).
- [ ] **Full skills taxonomy.** `apps/api/app/taxonomy/skills.py` is a small custom alias
      table. ESCO, O*NET, and Lightcast loaders and a skill-NER are pending.
- [ ] **pgvector / embedding storage.** Embeddings are re-computed in memory or stored as
      JSON. `job_descriptions.embedding` is unused; `bullets.embedding` is unused; no
      pgvector index or similarity search exists.
- [ ] **JD analysis cache.** Redis is reserved in Compose but unused; repeated JD analysis
      and embedding work is not cached.
- [ ] **Calibration.** Weights are fixed defaults from doc §4.3. No labelled
      resume/JD/outcome data, logistic regression / gradient boosting fit, or Spearman
      validation exists.
- [ ] **Fairness controls.** No explicit removal of name, gender, age, photo, nationality,
      or address signals before scoring, and no audit of score differences across groups.
      (Parseability does use name/contact presence as a parsing signal.)
- [ ] **Model/prompt version reproducibility.** Reports store some versions, but prompts and
      extraction models are `n/a` in the default path; a score cannot yet be replayed
      against an exact prompt/model build.
- [ ] **Multi-JD tailoring.** One master resume → many tailored versions is not implemented.

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
      `services/latex_worker` and attaches it to an internal network. Redis remains
      present but unused.
- [ ] **Queue/worker execution.** Jobs run via FastAPI `BackgroundTasks`
      (`apps/api/app/api/v1/jobs.py`). No Celery/Temporal/RQ/Dramatiq, no durable retries,
      no dead-letter handling, no cross-process progress.
- [~] **Resource limits.** The LaTeX worker has container CPU/memory/PID/time/output
      limits and a wall-clock timeout. General optimisation jobs still rely on the SSE
      300-second stream timeout and a stale-job setting.
- [ ] **S3/MinIO storage.** `storage_backend` is local-only; S3/MinIO/R2 support is absent.
- [ ] **Postgres in production path is only partially exercised.** Docker installs
      `.[postgres]`; local default is SQLite. No Postgres-specific test matrix runs in CI.
- [~] **Optional extras missing from the image.** Docker installs `.[postgres,pdf]` plus
      `poppler-utils`, so PyMuPDF and `pdftotext` run in the API container. The `nlp`
      extras and OCR stack (`ocr` extra + Tesseract) are not installed. The LaTeX worker
      itself is a separate image.
- [ ] **Observability.** No OpenTelemetry tracing, Prometheus metrics, Sentry, Langfuse
      LLM tracing, or dashboarding. Current logging is structured app logging only.
- [ ] **CI/CD.** No `.github/workflows`; no lint/test/build pipeline; no image publishing;
      no dependency or secret scanning.
- [ ] **Terraform / Kubernetes.** No IaC or K8s manifests; only a single Compose file.
- [ ] **TLS and encryption at rest.** No TLS termination, S3 SSE, or Postgres encryption
      configuration. PII is stored as plain local files/rows in the default setup.
- [ ] **PII redaction.** Microsoft Presidio is not installed; resumes are sent to LLM
      providers unredacted when a provider is configured.
- [ ] **Zero-retention provider controls.** No provider selection or policy enforcement for
      no-training/zero-retention terms; no self-hosted open-weight model path (vLLM/Ollama).
- [ ] **Audit log access.** `audit_log` rows are written by many endpoints but there is no
      read API, export, or UI.
- [ ] **Secret hygiene.** `.env.example` documents keys, but there is no secret manager or
      startup validation for production (for example, refusing `ATS_API_KEY=""`).
- [ ] **Security tests.** Hostile LaTeX patterns are unit-tested, but there is no fuzzing,
      zip-bomb test, SSRF resolution test matrix, or sandbox escape test (sandbox absent).
- [ ] **Type checking in CI.** `mypy` is not clean: it reports pre-existing errors in
      `apps/api/app/services/scoring/semantic.py` and
      `apps/api/app/services/ingest/pipeline.py`. `ruff` and `pytest` pass.

---

## 7. Data, evaluation, and calibration

- [ ] **Resume corpus.** No consented/synthetic/public resume corpus, and no 20+ LaTeX
      template corpus.
- [ ] **JD corpus.** No role/seniority-stratified job-description corpus.
- [ ] **Labelled outcomes.** No shortlisted/rejected labels, so score calibration and
      Spearman correlation cannot be measured.
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
| Celery/Redis or Temporal queue | `BackgroundTasks`, Redis reserved | Close in Phase 2 |
| pgvector in Postgres | JSON embeddings / in-memory hash | Close in Phase 2 |
| Multi-extractor parse fidelity | pypdf + optional PyMuPDF/`pdftotext` with token agreement | Tika remains optional |
| Sandboxed LaTeX compile | Worker + Docker/local fallback, opt-in; compile rollback | Tune limits with real workloads |
| LLM structuring + `instructor` | Heuristic structurer | Close when provider is enabled |
| LLM judge in score | Deterministic components only | Optional; decide explicitly |
| Monaco + PDF preview + diff viewer | Plain React panels | Close in Phase 3 |
| `/v1/versions/{id}/export` | Not present | Close in Phase 3 |
| `/v1/versions/{id}/changes/.../accept` | `/v1/jobs/{id}/changes/...` | Alias or document |
| Per-user auth (Clerk/Auth0) | Per-user API keys via `ATS_API_KEYS`; no SSO/plans | Close before multi-user |
| S3/MinIO storage | Local filesystem only | Close before hosted deployment |
| Presidio PII redaction | None | Close before external LLM use |

---

## 10. Suggested next sprint (ordered)

1. ~~**Editable proposal + metric workflow.**~~ Done in the P0 pass: `PATCH
   /v1/jobs/{id}/changes/{change_id}`, verifier re-run, Facts Bank recording, and the
   inline web editor. Next: expose the Facts Bank and version/export UI.
2. **Facts Bank + version/export UI.** Expose the existing facts and versions APIs, show a
   change log, and add at least TEX/JSON export.
3. **JD URL input.** Reuse the existing SSRF-guarded `/v1/jds` URL path in the UI.
4. **LaTeX worker spike.** One Tectonic container, no network, compile a Jake’s Resume
   sample, extract text with `pdftotext` + PyMuPDF, and return a parse-fidelity diff.
5. **Trained embeddings + pgvector.** Swap `HashedEmbedder` behind its interface, add the
   migration, and record the embedding model in reports.
6. **Golden set + CI.** Start with 20–50 resume/JD pairs, field-F1 parsing checks,
   hallucination checks, and a GitHub Actions pipeline.
