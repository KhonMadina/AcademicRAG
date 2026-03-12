# RAG Tuning & Improvement Playbook

This playbook implements the mini plan step-by-step for `rag_system` performance and quality tuning.

## Prerequisites

- Indexed documents exist in LanceDB tables.
- Eval set exists at `eval/retrieval_eval_set_v1.jsonl` (or provide `--eval-set`).
- Ollama/model services are running for generation/verifier checks.

## Step 1 — Baseline retrieval metrics

```bash
python -m rag_system.eval.run_retrieval_eval \
  --eval-set eval/retrieval_eval_set_v1.jsonl \
  --mode default \
  --k 5
```

Tracks quality (`retrieval_relevance_at_k`, `mrr_at_k`) and latency (`latency_ms_mean`, `p50`, `p95`, `max`).

## Step 2 — Retrieval tuning sweep with latency budget

```bash
python -m rag_system.eval.tune_retrieval_params \
  --eval-set eval/retrieval_eval_set_v1.jsonl \
  --mode default \
  --k 5 \
  --search-types hybrid,vector,fts \
  --dense-weights 0.4,0.5,0.6,0.7,0.8 \
  --ai-rerank \
  --reranker-top-k-values 5,10,15 \
  --max-latency-regression-pct 15
```

Selects the best candidate only if it stays within the configured p95 latency regression budget.

## Step 3 — Generation quality evaluation

```bash
python -m rag_system.eval.run_generation_quality_eval \
  --eval-set eval/retrieval_eval_set_v1.jsonl \
  --mode default \
  --verify \
  --search-type hybrid \
  --dense-weight 0.7 \
  --ai-rerank \
  --reranker-top-k 10
```

Checks groundedness/confidence from verifier output plus citation presence (`[S#]` tags in generated answers).

## Step 4 — Performance controls in runtime config

Runtime controls now available in retrieval pipeline config:

- `performance.query_result_cache.enabled`
- `performance.query_result_cache.ttl_seconds`
- `performance.query_result_cache.max_entries`
- `reranker.dynamic_top_k.enabled`
- `reranker.dynamic_top_k.short_query_tokens`
- `reranker.dynamic_top_k.short_query_top_k`
- `reranker.dynamic_top_k.long_query_min_top_k`

These reduce repeated-query latency and cap reranker work for short/simple queries.

## Step 5 — Regression + SLO gate checks

```bash
python -m rag_system.eval.check_quality_perf_gates \
  --baseline-retrieval eval/results/<baseline>.json \
  --candidate-retrieval eval/results/<candidate>.json \
  --answer-quality eval/results/<answer_quality>.json \
  --min-retrieval-relevance-delta 0.05 \
  --min-grounded-rate 0.80 \
  --min-citation-presence-rate 0.80 \
  --max-latency-regression-pct 15
```

Returns non-zero exit code on gate failures.

## Step 6 — One-command end-to-end execution

```bash
python -m rag_system.eval.run_tuning_improvement_plan \
  --eval-set eval/retrieval_eval_set_v1.jsonl \
  --mode default \
  --k 5 \
  --ai-rerank \
  --verify
```

Artifacts are written to `eval/results/` with one final summary JSON containing all step outputs.
