# Mini Plan — Improve AI Reranker, Context Expansion, and Answer Verification

Updated: 2026-03-12

## Goal
Improve answer quality for document-grounded questions while keeping response time predictable.

## Scope
Focus only on:
- `AI reranker`
- `Expand context window`
- `Verify answer`

## Success Targets
- Reduce p95 end-to-end chat latency for RAG queries to under 45s on the current local setup.
- Keep or improve retrieval relevance and groundedness versus current baseline.
- Avoid multi-minute responses for questions that do not need all advanced steps.

## Current Risks
- `AI reranker` adds a heavy second-stage ranking pass over too many chunks.
- `Expand context window` can inflate prompt size and slow final generation.
- `Verify answer` adds an extra LLM pass even when the answer is already well grounded.
- All three features together compound latency.

## Mini Plan

### Phase 1 — Baseline and instrumentation
Owner: Backend
Effort: 0.5–1 day

Tasks:
- Capture baseline latency for 20 representative RAG questions.
- Break timing into:
  - retrieval
  - rerank
  - context expansion
  - answer generation
  - verification
- Record quality signals:
  - relevance@k
  - grounded answer rate
  - citation presence rate

Deliverables:
- Baseline JSON report in `eval/results/`
- Per-stage timing fields exposed in diagnostics or logs

Acceptance criteria:
- Can identify which of the three features contributes most to p95 latency.

### Phase 2 — AI reranker optimization
Owner: Backend
Effort: 1–2 days

Tasks:
- Apply reranker only to a smaller candidate pool.
- Test `reranker_top_k` values: 3, 5, 8, 10.
- Skip reranker for:
  - very short queries
  - obvious single-document lookup questions
  - low-candidate retrieval sets
- Cache reranked results for repeated queries within a short TTL.

Recommended default:
- `ai_rerank = true` only for complex queries
- `reranker_top_k = 5`
- `retrieval_k = 8–10` before rerank

Acceptance criteria:
- Reranker improves answer quality on the eval set.
- Reranker stage latency drops materially versus current baseline.

### Phase 3 — Context expansion optimization
Owner: Backend
Effort: 1 day

Tasks:
- Expand neighbors only for top-ranked chunks, not all retrieved chunks.
- Limit expansion by token budget, not only by chunk count.
- Test `context_window_size` values: 0 and 1.
- Disable expansion when chunk text already contains enough local context.

Recommended default:
- `context_expand = false` by default
- enable only for summarization/explanation questions
- `context_window_size = 1` max

Acceptance criteria:
- Prompt size stays bounded.
- Expansion improves answer completeness without large latency regression.

### Phase 4 — Verification optimization
Owner: Backend
Effort: 1–2 days

Tasks:
- Run verifier only when confidence is needed, not on every answer.
- Gate verification on heuristics such as:
  - low retrieval score spread
  - conflicting evidence
  - few citations
  - long synthesized answers
- Add a timeout budget for verifier calls.
- Return answer first, then optionally attach verification metadata if streaming mode is active.

Recommended default:
- `verify = false` by default
- enable on demand for high-stakes or low-confidence answers
- verifier timeout: 8–12 seconds

Acceptance criteria:
- Verification no longer doubles latency for routine questions.
- Verified answers still improve groundedness where enabled.

### Phase 5 — Runtime policy for quality/performance balance
Owner: Full-stack + Backend
Effort: 1 day

Tasks:
- Introduce two presets in the UI and server policy:
  - `Fast`: reranker off, expansion off, verification off
  - `Balanced`: reranker conditional, expansion conditional, verification off by default
- Keep advanced toggles available manually.
- Show helper text warning that enabling all three increases latency.

Recommended default preset:
- `Balanced`

Acceptance criteria:
- Normal users avoid slow combinations by default.
- Advanced users can still opt into maximum quality.

## Experiment Matrix
Use the existing evaluation flow to compare these combinations:

1. Baseline fast
   - rerank off
   - expand off
   - verify off
2. Rerank only
   - rerank on
   - top_k 5
3. Rerank + small expansion
   - rerank on
   - expansion on
   - window 1
4. Conditional verify
   - rerank on
   - expansion conditional
   - verify on only for low-confidence cases

## Recommended Rollout Order
1. Instrument timings
2. Shrink reranker workload
3. Bound context expansion
4. Gate verification
5. Ship presets and safer defaults

## Expected Outcome
- Large reduction in worst-case latency
- Better quality/latency tradeoff for document Q&A
- Fewer cases where the system spends minutes on a single answer

## Related Files
- `rag_system/agent/loop.py`
- `rag_system/pipelines/retrieval_pipeline.py`
- `rag_system/api_server.py`
- `src/components/ui/session-chat.tsx`
- `src/components/ui/chat-settings-modal.tsx`
- `Documentation/rag_tuning_improvement_playbook.md`
