# AcademicRAG Implementation Task Board (Feasible Execution Plan)

This board translates the improvement roadmap into executable tickets.

## Planning Assumptions
- Team: 2 engineers (1 backend/platform, 1 full-stack)
- Cadence: 1-week sprints
- Target duration: 8 weeks
- Priority scale: P0 (must), P1 (high), P2 (nice)
- Effort scale: S (0.5-1 day), M (2-3 days), L (4-5 days)

## Step-by-Step Execution Status
- Updated: 2026-03-06
- Completed:
  - Sprint 1 / T1.1: Dependency cleanup in root `requirements.txt` (duplicate entries removed)
  - Sprint 1 / T1.2: Added `.env.example` and startup environment validation in `run_system.py`
  - Sprint 1 / T1.3: Aligned quick-start docs to primary `run_system.py` startup path
  - Sprint 2 / T2.2: Unified backend and RAG API error schema (`success`, `error`, `error_code`, `details`)
  - Sprint 2 / T2.1: Added timeout, retry/backoff, and circuit-breaker wrappers for Ollama model calls
  - Sprint 2 / T2.3: Added liveness/readiness endpoints and launcher readiness status reporting
  - Sprint 3 / T3.1: Added automated backend endpoint integration tests (happy paths + validation errors)
  - Sprint 3 / T3.2: Added retrieval pipeline smoke tests for empty and indexed query behavior
  - Sprint 3 / T3.3: Added frontend E2E happy-path test (index creation -> upload -> build -> chat response rendering)
  - Sprint 4 / T4.1: Added dynamic memory-aware indexing batch controls with safe min/max caps
  - Sprint 4 / T4.2: Added index build stage/progress reporting (queued/parsing/enriching/embedding/storing/done/failed)
  - Sprint 4 / T4.3: Added resumable indexing checkpoints with completed/pending file metadata and resume controls
  - Sprint 5 / T5.1: Added versioned retrieval eval set (`eval/retrieval_eval_set_v1.jsonl`) and baseline scorer (`rag_system/eval/run_retrieval_eval.py`)
  - Sprint 5 / T5.3: Added retrieval diagnostics endpoint (`POST /retrieval/diagnostics`) with pre-rerank/post-rerank top-k scores
  - Sprint 6 / T6.1: Replaced generic chat/upload/index failures with actionable recovery guidance in frontend error handling
  - Sprint 6 / T6.2: Added index status badges (building/ready/failed) and last-updated timestamps in index picker/details UI
  - Sprint 7 / T7.1: Added rotating service logs and request correlation IDs (`X-Request-ID`) across backend and RAG API
  - Sprint 7 / T7.2: Added lightweight metrics endpoints (`GET /metrics`) for backend and RAG API with API latency, indexing duration, and semantic cache hit-rate
  - Sprint 7 / T7.3: Added production runbook with startup/shutdown, backup/restore, and incident checklist (`Documentation/production_runbook.md`)
  - Sprint 8 / T8.1: Synchronized core docs (quick start, install, deployment, architecture) with current launcher-first startup path, backend→RAG API flow, and metrics endpoints
  - Sprint 8 / T8.2: Added known limits and capacity guide with practical guardrails for file size, model memory, latency targets, and retrieval/indexing knobs (`Documentation/known_limits_capacity_guide.md`)
  - Sprint 8 / T8.3: Added release checklist + dry-run report with startup/health/metrics smoke evidence (`Documentation/release_checklist_dry_run.md`)
- Next In Progress:
  - Post-M4: Nice-to-have backlog prioritization
- Notes:
  - Sprint 5 / T5.2 tooling is implemented (`rag_system/eval/tune_retrieval_params.py`) with extended scorer knobs in (`rag_system/eval/run_retrieval_eval.py`).
  - Latest compact sweep report: `eval/results/retrieval_tuning_latest.json` (no measurable gain on current table/data; revisit after expanding eval set or corpus diversity).

---

## Sprint 1 — Foundation Stabilization

### T1.1 Dependency cleanup and lock alignment
- Priority: P0
- Effort: M
- Owner: Platform
- Dependencies: None
- Deliverables:
  - Remove duplicated packages from `requirements.txt`
  - Split runtime vs dev/test dependencies (if needed)
  - Verify frontend and backend dependency compatibility
- Acceptance Criteria:
  - Fresh install succeeds on clean machine
  - No duplicate entries in dependency manifests
  - Health check still passes

### T1.2 Configuration contract + startup validation
- Priority: P0
- Effort: M
- Owner: Backend
- Dependencies: T1.1
- Deliverables:
  - Update `.env.example` with required + optional vars
  - Add startup config validator for missing/invalid env values
  - Fail fast with actionable errors
- Acceptance Criteria:
  - Missing required env var produces explicit error message
  - Valid config boots all services normally

### T1.3 Docs alignment for one startup path
- Priority: P1
- Effort: S
- Owner: Full-stack
- Dependencies: T1.2
- Deliverables:
  - Make `run_system.py` the primary startup path in docs
  - Mark manual startup as advanced troubleshooting path
- Acceptance Criteria:
  - Quick start follows one clear path with no contradictory steps

---

## Sprint 2 — Reliability Hardening

### T2.1 Resilient model client wrappers
- Priority: P0
- Effort: L
- Owner: Backend
- Dependencies: T1.2
- Deliverables:
  - Add timeout/retry/backoff for Ollama and external model calls
  - Add circuit-breaker behavior for repeated failures
- Acceptance Criteria:
  - Simulated model outages return controlled errors
  - Requests do not hang indefinitely

### T2.2 Unified API error schema
- Priority: P0
- Effort: M
- Owner: Backend
- Dependencies: T2.1
- Deliverables:
  - Standardize error response payload shape across endpoints
  - Include user-safe message + technical code
- Acceptance Criteria:
  - All failing endpoints return the same JSON error format
  - Frontend can display error messages consistently

### T2.3 Health/readiness checks improvement
- Priority: P1
- Effort: M
- Owner: Platform
- Dependencies: T2.1
- Deliverables:
  - Add readiness checks for model server and key endpoints
  - Distinguish liveness vs readiness
- Acceptance Criteria:
  - Health script reports per-service readiness clearly

---

## Sprint 3 — Testing Baseline (Highest ROI)

### T3.1 Backend endpoint tests
- Priority: P0
- Effort: L
- Owner: Backend
- Dependencies: T2.2
- Deliverables:
  - Add tests for chat/session/index API routes
  - Include success + error-path tests
- Acceptance Criteria:
  - Test suite runs locally and in CI
  - Core API routes covered by automated tests

### T3.2 Retrieval pipeline smoke tests
- Priority: P0
- Effort: M
- Owner: Backend
- Dependencies: T3.1
- Deliverables:
  - Add tests for empty index, indexed query, source return shape
- Acceptance Criteria:
  - Smoke tests pass against seeded minimal test data

### T3.3 Frontend E2E happy-path test
- Priority: P1
- Effort: L
- Owner: Full-stack
- Dependencies: T3.1
- Deliverables:
  - Automate upload -> index build -> ask question -> render answer
- Acceptance Criteria:
  - E2E test passes in CI (or nightly if runtime-heavy)

---

## Sprint 4 — Indexing Performance and Safety

### T4.1 Memory-aware indexing controls
- Priority: P0
- Effort: M
- Owner: Backend
- Dependencies: T3.2
- Deliverables:
  - Add configurable batch/chunk controls for large docs
  - Enforce safe defaults
- Acceptance Criteria:
  - Large PDF indexing no longer crashes under typical memory limits

### T4.2 Index job progress and stage reporting
- Priority: P1
- Effort: M
- Owner: Full-stack
- Dependencies: T4.1
- Deliverables:
  - Expose progress state: queued, parsing, embedding, storing, done, failed
- Acceptance Criteria:
  - UI reflects current job stage and completion percentage

### T4.3 Resumable indexing metadata
- Priority: P2
- Effort: L
- Owner: Backend
- Dependencies: T4.1
- Deliverables:
  - Persist partial progress markers for interrupted runs
- Acceptance Criteria:
  - Interrupted jobs can be resumed without full restart

---

## Sprint 5 — Retrieval Quality Optimization

### T5.1 Build a small evaluation set
- Priority: P0
- Effort: M
- Owner: Full-stack
- Dependencies: T3.2
- Deliverables:
  - 25-50 representative questions with expected evidence docs
- Acceptance Criteria:
  - Eval set versioned and reusable for tuning

### T5.2 Hybrid retrieval parameter tuning
- Priority: P0
- Effort: L
- Owner: Backend
- Dependencies: T5.1
- Deliverables:
  - Tune BM25/vector/rerank weights using eval set
- Acceptance Criteria:
  - Measurable improvement vs baseline on retrieval relevance

### T5.3 Retrieval diagnostics endpoint
- Priority: P1
- Effort: M
- Owner: Backend
- Dependencies: T5.2
- Deliverables:
  - Endpoint returns pre-rerank and post-rerank top-k with scores
- Acceptance Criteria:
  - Engineers can inspect ranking behavior for debugging

---

## Sprint 6 — Minimal UX Improvements

### T6.1 Actionable upload/chat errors
- Priority: P1
- Effort: M
- Owner: Full-stack
- Dependencies: T2.2
- Deliverables:
  - Replace generic failures with recovery guidance in UI
- Acceptance Criteria:
  - Common failures map to clear user actions

### T6.2 Index status badges and timestamps
- Priority: P1
- Effort: S
- Owner: Full-stack
- Dependencies: T4.2
- Deliverables:
  - Add statuses: building, ready, failed + last-updated
- Acceptance Criteria:
  - Index list communicates state without opening details

---

## Sprint 7 — Observability and Operations

### T7.1 Log rotation and correlation IDs
- Priority: P1
- Effort: M
- Owner: Platform
- Dependencies: T2.2
- Deliverables:
  - Add structured logs with request correlation IDs
  - Configure file rotation
- Acceptance Criteria:
  - One user request can be traced across services

### T7.2 Lightweight metrics
- Priority: P1
- Effort: M
- Owner: Platform
- Dependencies: T7.1
- Deliverables:
  - Track API latency, indexing duration, cache hit-rate
- Acceptance Criteria:
  - Metrics visible in logs or simple dashboard endpoint

### T7.3 Production runbook
- Priority: P1
- Effort: S
- Owner: Platform
- Dependencies: T7.1
- Deliverables:
  - Startup/shutdown, backup/restore, incident checklist
- Acceptance Criteria:
  - New operator can recover service from runbook only

---

## Sprint 8 — Release Hardening

### T8.1 Documentation synchronization
- Priority: P0
- Effort: M
- Owner: Full-stack
- Dependencies: All prior sprints
- Deliverables:
  - Align architecture, quick-start, deployment docs to actual behavior
- Acceptance Criteria:
  - No doc step is stale or contradictory

### T8.2 Known limits and capacity guide
- Priority: P1
- Effort: S
- Owner: Platform
- Dependencies: T8.1
- Deliverables:
  - Publish practical limits (file sizes, model memory, expected latency)
- Acceptance Criteria:
  - Users have clear expectations and guardrails

### T8.3 Release checklist + dry run
- Priority: P0
- Effort: M
- Owner: Team
- Dependencies: T8.1
- Deliverables:
  - End-to-end clean-machine install and smoke validation
- Acceptance Criteria:
  - Team can reproduce deployment from docs in under 30 minutes

---

## Cross-Cutting Definition of Done
- Code merged with review
- Automated tests pass
- Failure cases handled and user-visible errors are actionable
- Relevant docs updated in the same PR
- No regression in startup and health checks

## Suggested Milestones
- M1 (End Sprint 2): Stable startup + resilient error handling
- M2 (End Sprint 4): Baseline test coverage + safer indexing
- M3 (End Sprint 6): Improved retrieval quality + cleaner UX
- M4 (End Sprint 8): Release-ready, documented, observable system

## Nice-to-Have Backlog (After M4)
- Multi-format document support beyond PDF
- Advanced cache invalidation policies
- Dataset/version management for index collections
- Role-based access control for multi-user deployment
