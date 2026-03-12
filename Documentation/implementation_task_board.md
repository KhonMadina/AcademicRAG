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
  - Post-M4 / T9.1: Per-stage latency baseline for rerank/context/verify
  - Post-M4 / T9.2: Conditional AI reranker policy and smaller rerank candidate pool
  - Post-M4 / T9.3: Context expansion guardrails and token-budget caps
  - Post-M4 / T9.4: Conditional verification policy with timeout budget
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

---

## Post-M4 Focused Performance + Quality Tickets

These tickets operationalize the mini plan in [Documentation/mini_plan_reranker_context_verify.md](Documentation/mini_plan_reranker_context_verify.md).

### T9.1 Per-stage latency baseline for rerank/context/verify
- Priority: P0
- Effort: M
- Owner: Backend
- Dependencies: None
- Deliverables:
  - Add per-stage timing for retrieval, rerank, context expansion, generation, and verification
  - Persist baseline reports for a representative RAG query set in `eval/results/`
  - Expose timing breakdowns in logs or diagnostics for troubleshooting
- Acceptance Criteria:
  - Team can identify which stage dominates p95 latency
  - Baseline report exists for before/after comparisons

### T9.2 Conditional AI reranker policy
- Priority: P0
- Effort: L
- Owner: Backend
- Dependencies: T9.1
- Deliverables:
  - Apply reranker only for complex or ambiguous queries
  - Reduce default rerank candidate pool and tune `reranker_top_k`
  - Add short-TTL cache for repeated rerank results when safe
- Acceptance Criteria:
  - Reranker quality benefit is preserved on eval set
  - Reranker stage latency is measurably lower than current baseline
  - Default runtime avoids expensive rerank on simple lookups

### T9.3 Context expansion guardrails
- Priority: P0
- Effort: M
- Owner: Backend
- Dependencies: T9.1
- Deliverables:
  - Expand neighbors only for top-ranked chunks
  - Add token-budget cap for expanded context
  - Tune `context_window_size` defaults for speed-safe operation
- Acceptance Criteria:
  - Prompt growth is bounded for large queries
  - Expanded-context mode improves completeness without major p95 regression

### T9.4 Conditional verification policy
- Priority: P0
- Effort: M
- Owner: Backend
- Dependencies: T9.1
- Deliverables:
  - Run verifier only for low-confidence or high-risk answers
  - Add verifier timeout budget and controlled fallback behavior
  - Return verification metadata without blocking routine answers when possible
- Acceptance Criteria:
  - Verification no longer doubles latency for common queries
  - Groundedness improves for answers that do trigger verification

### T9.5 UI presets for quality/performance balance
- Priority: P1
- Effort: M
- Owner: Full-stack
- Dependencies: T9.2, T9.3, T9.4
- Deliverables:
  - Add `Fast` and `Balanced` presets in chat settings
  - Keep advanced toggles for manual override
  - Add helper text warning when `AI reranker`, `Expand context window`, and `Verify answer` are all enabled together
- Acceptance Criteria:
  - Default UX avoids multi-minute responses for standard questions
  - Users can still opt into maximum-quality behavior explicitly

### T9.6 Eval gate for latency/quality tradeoff
- Priority: P1
- Effort: M
- Owner: Backend
- Dependencies: T9.2, T9.3, T9.4
- Deliverables:
  - Add regression gate for p95 latency, groundedness, and citation presence
  - Document accepted operating ranges for balanced mode
  - Save comparison artifacts for baseline vs candidate configurations
- Acceptance Criteria:
  - Changes that improve quality but violate latency budget are automatically flagged
  - Release decisions can be made from reproducible metrics

## Suggested Post-M4 Sprint Order

### Sprint 9 — Measure and de-risk
- Primary goal: establish latency truth before tuning
- Tickets:
  - T9.1 Per-stage latency baseline for rerank/context/verify
  - T9.6 Eval gate for latency/quality tradeoff
- Why first:
  - prevents blind tuning
  - gives reproducible before/after evidence
- Exit criteria:
  - baseline report saved
  - p50/p95 stage timing visible
  - regression gate runnable locally

#### Sprint 9 engineering subtasks by file

1. `rag_system/agent/loop.py`
  - Add per-stage timers for:
    - triage
    - retrieval
    - rerank
    - context expansion
    - answer generation
    - verification
  - Return a structured `timings_ms` object in agent results.
  - Preserve existing result schema so callers do not break.

2. `rag_system/pipelines/retrieval_pipeline.py`
  - Expose retrieval-stage timing details separately from final synthesis.
  - Split timing fields for base retrieval, rerank, and context expansion.
  - Keep timing capture lightweight and optional where possible.

3. `rag_system/api_server.py`
  - Include stage timings in `POST /chat`, `POST /chat/stream`, and `POST /retrieval/diagnostics` responses where appropriate.
  - Add aggregated stage metrics to existing service metrics snapshot if practical.
  - Ensure request logs include total duration and stage summary for slow requests.

4. `rag_system/eval/run_retrieval_eval.py`
  - Persist new latency fields for each evaluated query:
    - total latency
    - retrieval latency
    - rerank latency
    - context expansion latency
  - Add summary stats for mean, p50, p95, and max.

5. `rag_system/eval/run_generation_quality_eval.py`
  - Record verification latency separately from answer generation latency.
  - Include groundedness and citation metrics alongside timing summaries.

6. `rag_system/eval/check_quality_perf_gates.py`
  - Add gate checks for p95 total latency and, if available, p95 rerank/verification latency.
  - Keep existing quality gates intact.
  - Fail clearly when candidate quality improves but latency budget is exceeded.

7. `rag_system/eval/run_tuning_improvement_plan.py`
  - Surface the new timing fields in the final combined summary artifact.
  - Print a compact before/after table for quality and latency.

8. `Documentation/rag_tuning_improvement_playbook.md`
  - Add a short section for reading the new stage-level timing outputs.
  - Document the latency budget used for balanced mode decisions.

9. Tests
  - Add or extend tests in:
    - `rag_system/test_retrieval_pipeline.py`
    - `rag_system/test_quality_perf_gates.py`
    - `rag_system/test_retrieval_eval_runner.py`
  - Verify timing fields exist, remain numeric, and do not break older consumers.

#### Sprint 9 execution order
- Step 1: instrument `rag_system/agent/loop.py`
- Step 2: expose timings from `rag_system/pipelines/retrieval_pipeline.py`
- Step 3: return timings via `rag_system/api_server.py`
- Step 4: persist and summarize timings in eval scripts
- Step 5: enforce thresholds in `rag_system/eval/check_quality_perf_gates.py`
- Step 6: update docs and regression tests

### Sprint 10 — Reduce heavy retrieval overhead
- Primary goal: improve quality without large latency spikes
- Tickets:
  - T9.2 Conditional AI reranker policy
  - T9.3 Context expansion guardrails
- Why second:
  - these two settings are the biggest controllable retrieval-time multipliers
  - they affect both answer quality and prompt size
- Exit criteria:
  - reranker workload reduced on simple queries
  - expanded context bounded by token budget
  - balanced mode stays within target latency envelope

### Sprint 11 — Make verification safe and ship UX controls
- Primary goal: keep trust features without blocking normal answers
- Tickets:
  - T9.4 Conditional verification policy
  - T9.5 UI presets for quality/performance balance
- Why third:
  - verification policy depends on earlier retrieval quality signals
  - presets are safest after backend behavior is stabilized
- Exit criteria:
  - verifier runs only on selected cases
  - `Fast` and `Balanced` presets available in UI
  - default path avoids multi-minute answers

## Recommended Delivery Sequence
1. Instrumentation and eval gate
2. Conditional reranker
3. Context expansion caps
4. Conditional verifier with timeout
5. UI presets and warning copy

## Recommended Default Operating Mode After Rollout
- Default preset: `Balanced`
- `AI reranker`: conditional
- `Expand context window`: conditional, max window size `1`
- `Verify answer`: off by default, on only for selected cases
