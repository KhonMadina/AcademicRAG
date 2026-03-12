# Sprint 9 Checklist — `rag_system/agent/loop.py`

Updated: 2026-03-12

## Objective
Add stage-level timing instrumentation to the agent without changing user-visible behavior.

## Target File
- `rag_system/agent/loop.py`

## Implementation Checklist

### 1. Add a result timing container
- Create a local `timings_ms` dictionary inside `_run_async()`.
- Keep keys stable and explicit.
- Suggested keys:
  - `triage`
  - `retrieval`
  - `rerank`
  - `context_expand`
  - `generation`
  - `verification`
  - `total`

Acceptance:
- Every successful result includes a `timings_ms` object.
- Missing phases default to `0` or are omitted consistently.

### 2. Time triage separately
- Measure elapsed time around `_triage_query_async()`.
- Store duration in `timings_ms.triage`.

Acceptance:
- Direct-answer and RAG flows both report triage timing.

### 3. Time direct-answer generation
- In the `direct_answer` branch, measure only model answer generation.
- Do not mix triage and generation timings.
- Store duration in `timings_ms.generation`.

Acceptance:
- Direct-answer results include `triage`, `generation`, and `total`.

### 4. Time retrieval-path sub-stages
- For RAG flows, capture timing around retrieval work.
- Prefer to consume sub-stage timings returned from `retrieval_pipeline.run()`.
- If not yet available, add temporary fallback timing around the full retrieval call and map it to `retrieval`.

Acceptance:
- RAG results include at least `retrieval` and `total`.
- Later retrieval-pipeline timing fields can be merged in without schema churn.

### 5. Time answer composition/generation for RAG
- Measure final answer generation separately from document retrieval.
- For decomposed-query flows:
  - time composition separately if possible,
  - map composition to `generation` for now.
- For single-query synthesis:
  - time the synthesis call only.

Acceptance:
- Retrieval and generation are not combined into one opaque number.

### 6. Time verification separately
- Measure only the verifier call block.
- Store in `timings_ms.verification`.
- If verification is skipped, set `verification` to `0`.

Acceptance:
- Verification timing is present even when disabled/skipped.

### 7. Add total request timing
- Measure full `_run_async()` elapsed time.
- Store as `timings_ms.total` before return.

Acceptance:
- `total` is always present.
- `total` is greater than or equal to all component timings.

### 8. Attach timings to all return paths
- Ensure cache hits, direct answers, graph queries, decomposed RAG, and standard RAG all return `timings_ms`.
- For semantic cache hits, include:
  - `triage`
  - `total`
  - optionally `cache_hit: true` in metadata if useful

Acceptance:
- No code path returns a result without timing data.

### 9. Preserve compatibility
- Do not break current fields:
  - `answer`
  - `source_documents`
  - `verification`
- Add timing fields as additive metadata only.

Acceptance:
- Existing API consumers continue to work without modification.

### 10. Add debug logging for slow phases
- Add lightweight logging for unusually slow phases.
- Suggested threshold examples:
  - rerank > 3000 ms
  - verification > 8000 ms
  - total > 15000 ms

Acceptance:
- Slow-path logs help diagnose latency spikes without flooding normal logs.

## Suggested Coding Order
1. Add `timings_ms` initialization and `total` timer.
2. Instrument triage.
3. Instrument direct-answer generation.
4. Instrument verification.
5. Add additive timing attachment to all returns.
6. Integrate finer retrieval timings once `retrieval_pipeline.py` exposes them.

## Suggested Test Follow-up
After implementation, update:
- `rag_system/test_retrieval_pipeline.py`
- `rag_system/test_retrieval_eval_runner.py`
- `rag_system/test_quality_perf_gates.py`

Minimum assertions:
- `timings_ms` exists
- values are numeric
- `total` is present
- direct-answer path still works
- RAG path still works

## Done Criteria
- `rag_system/agent/loop.py` returns stable timing metadata for every major path.
- No existing tests regress.
- Timing fields are ready for API and eval-layer propagation.
