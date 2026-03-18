# AcademicRAG Known Limits and Capacity Guide

This guide documents practical operating limits and tuning guardrails for AcademicRAG.

It separates:
- **Hard/implemented limits** (enforced by code), and
- **Operational recommendations** (for stable production behavior).

---

## 1. Capacity Baseline (Practical Expectations)

These are the currently documented service-level expectations for a healthy local deployment:

- **Index creation**: target < 2 minutes per 100MB document (acceptable)
- **Complex query response**: target < 30 seconds (acceptable)
- **Total system memory**: keep under 8GB for acceptable operation

For stronger performance, prefer:

- **Index creation**: < 1 minute per 100MB document
- **Complex query response**: < 10 seconds
- **Memory headroom**: 16GB+ system RAM

> These expectations come from the current deployment benchmarks and will vary by CPU/GPU, model sizes, and document complexity.

---

## 2. File Size and Document Guardrails

### 2.1 Implemented behavior

- Large-PDF memory guard variables are supported:
  - `RAG_LARGE_PDF_SIZE_MB` (default commonly used: `40`)
  - `RAG_LARGE_PDF_PAGE_THRESHOLD` (default commonly used: `150`)
- When PDFs exceed configured thresholds, the system can bypass heavy preprocess and fall back to lightweight extraction.

### 2.2 Recommended operating limits

- **Predictable indexing quality/performance**: keep individual PDFs at or below approximately `40MB` or `150` pages unless you intentionally tune for larger files.
- For very large corpora, split into multiple indexes rather than one oversized batch.
- If indexing throughput collapses or OOM symptoms appear, lower chunk and batch settings before changing models.

---

## 3. Memory and Batch Control Limits (Implemented)

Indexing pipeline includes memory-aware batch tuning with environment-controlled bounds:

- `RAG_MAX_EMBED_BATCH` default: `24`
- `RAG_MAX_ENRICH_BATCH` default: `24`
- `RAG_MIN_EMBED_BATCH` default: `4`
- `RAG_MIN_ENRICH_BATCH` default: `2`
- `RAG_LOW_MEMORY_THRESHOLD_MB` default: `3072`
- `RAG_INDEXING_TARGET_MEM_MB` default: `1024`

Runtime behavior:

- The pipeline estimates chunk memory pressure.
- It auto-reduces embed/enrich batch sizes within min/max safety bounds.
- It enters low-memory mode when available RAM drops below threshold.

### Recommended starting values

For moderate hardware (8–16GB RAM):

- `batch_size_embed`: `25` to `50`
- `batch_size_enrich`: `10` to `25`
- `chunk_size`: `512`
- `chunk_overlap`: `64`

For constrained hardware (<8GB free at runtime):

- `batch_size_embed`: `8` to `24`
- `batch_size_enrich`: `4` to `12`
- keep enrichment enabled only when needed

---

## 4. Retrieval and Chat Guardrails

### 4.1 Implemented defaults and clamps

- `retrieval_k` defaults to `20` (default mode) and is clamped to at least `1` in diagnostics.
- `dense_weight` is clamped to `[0.0, 1.0]`.
- `semantic_cache_threshold` default is `0.98`.
- `cache_scope` default is `global`.

### 4.2 Recommended operating ranges

- `retrieval_k`: `10` to `30` for typical document QA.
- `reranker_top_k`: `5` to `20`.
- `dense_weight`: `0.6` to `0.8` for balanced hybrid search.
- keep `semantic_cache_threshold` high (`>=0.95`) to avoid stale/over-broad cache hits.

---

## 5. Model Footprint Guidance

- Primary quality model (`gemma3:12b-cloud`) requires materially more RAM/compute than lightweight model (`gemma3:12b-cloud`).
- If latency or memory pressure rises:
  1. switch generation to lighter model,
  2. reduce retrieval and reranker breadth,
  3. reduce indexing batch sizes,
  4. then scale hardware.

---

## 6. Capacity Warning Signals

Investigate immediately if any are sustained:

- readiness endpoints fail for >2 minutes,
- repeated `5xx` responses from backend or RAG API,
- `/metrics` shows sudden latency spikes (`max_ms` > 3x baseline),
- indexing failure count increases during normal load,
- semantic cache hit-rate collapses after deploy/config change.

---

## 7. Tuning Workflow (Safe Sequence)

When capacity is exceeded, tune in this order:

1. **Indexing safety first**: reduce `batch_size_embed` and `batch_size_enrich`.
2. **Retrieval cost**: reduce `retrieval_k` and `reranker_top_k`.
3. **Model load**: switch to lighter generation/enrichment model.
4. **Document strategy**: split large files and distribute across indexes.
5. **Hardware scaling**: add RAM/GPU only after software tuning.

---

## 8. Validation Checklist After Tuning

After any capacity change, verify:

- `GET /health` and `GET /health/ready` on ports `8000` and `8001`,
- `GET /metrics` on both services,
- one representative index build,
- one representative chat query,
- no recurring errors in `logs/backend_server.log`, `logs/rag_api_server.log`, and `logs/system.log`.
