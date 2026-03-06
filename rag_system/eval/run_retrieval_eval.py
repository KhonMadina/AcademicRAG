#!/usr/bin/env python3
"""Run retrieval-only evaluation against a versioned JSONL eval set.

Each eval row should include:
  - id
  - query
  - expected_evidence_docs: list[str]
  - expected_answer_notes (optional)

Metrics reported:
  - citation_hit_rate@k: fraction of rows where at least one expected doc is in top-k
  - mrr@k: mean reciprocal rank of the first expected doc found in top-k
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from rag_system.main import get_agent


def _safe_json_loads(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _discover_table_names(retriever: Any) -> List[str]:
    try:
        db = retriever.db_manager.db
        if hasattr(db, "table_names"):
            names = db.table_names()
            if isinstance(names, list):
                return [name for name in names if isinstance(name, str)]
    except Exception:
        return []
    return []


def _resolve_table_name(preferred: Optional[str], available_tables: Sequence[str]) -> Optional[str]:
    if preferred and preferred in available_tables:
        return preferred

    table_pool = [name for name in available_tables if isinstance(name, str) and name.strip()]
    if not table_pool:
        return preferred

    if preferred:
        prefix = preferred.split("_v", 1)[0]
        prefix_matches = sorted([name for name in table_pool if name.startswith(prefix)], reverse=True)
        if prefix_matches:
            return prefix_matches[0]

    text_tables = sorted([name for name in table_pool if name.startswith("text_pages")], reverse=True)
    if text_tables:
        return text_tables[0]

    return sorted(table_pool)[0]


def _normalize_identifier(value: str) -> str:
    compact = (value or "").strip().lower().replace("\\", "/")
    if not compact:
        return ""
    return " ".join(compact.replace("_", " ").replace("-", " ").split())


def _identifier_variants(value: str) -> List[str]:
    normalized = _normalize_identifier(value)
    if not normalized:
        return []

    variants = {normalized}
    base = normalized.rsplit("/", 1)[-1]
    variants.add(base)
    if "." in base:
        variants.add(base.rsplit(".", 1)[0])
    return sorted(variants)


def _match_expected_to_retrieved(expected: str, retrieved: str) -> bool:
    expected_variants = _identifier_variants(expected)
    retrieved_variants = _identifier_variants(retrieved)
    if not expected_variants or not retrieved_variants:
        return False

    for expected_variant in expected_variants:
        for retrieved_variant in retrieved_variants:
            if expected_variant == retrieved_variant:
                return True
            if expected_variant in retrieved_variant:
                return True
            if retrieved_variant in expected_variant:
                return True
    return False


def _extract_doc_identifiers(doc: Dict[str, Any]) -> List[str]:
    identifiers: List[str] = []
    metadata = _safe_json_loads(doc.get("metadata"))

    candidates = [
        doc.get("document_id"),
        doc.get("document_title"),
        doc.get("title"),
        doc.get("source"),
        metadata.get("document_id"),
        metadata.get("document_title"),
        metadata.get("title"),
        metadata.get("source"),
        metadata.get("file_path"),
        metadata.get("filename"),
    ]

    for value in candidates:
        if isinstance(value, str) and value.strip():
            identifiers.extend(_identifier_variants(value))

    deduped = []
    seen = set()
    for item in identifiers:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _find_first_match_rank(expected_docs: Sequence[str], retrieved_docs: Sequence[Dict[str, Any]], k: int) -> Optional[int]:
    if not expected_docs:
        return None

    for rank, doc in enumerate(retrieved_docs[:k], start=1):
        doc_identifiers = _extract_doc_identifiers(doc)
        for expected in expected_docs:
            if any(_match_expected_to_retrieved(expected, found) for found in doc_identifiers):
                return rank
    return None


def load_eval_rows(eval_set_path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(eval_set_path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

            if not isinstance(row, dict):
                raise ValueError(f"Invalid eval row at line {line_number}: expected object")

            query = row.get("query")
            expected_docs = row.get("expected_evidence_docs")
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"Invalid eval row at line {line_number}: missing query")
            if not isinstance(expected_docs, list):
                raise ValueError(
                    f"Invalid eval row at line {line_number}: expected_evidence_docs must be a list"
                )

            rows.append(row)
    return rows


def evaluate(
    eval_rows: Sequence[Dict[str, Any]],
    *,
    mode: str,
    table_name: Optional[str],
    k: int,
    search_type: str,
    dense_weight: Optional[float] = None,
    ai_rerank: bool = False,
    reranker_top_k: Optional[int] = None,
) -> Dict[str, Any]:
    agent = get_agent(mode)
    retrieval_pipeline = agent.retrieval_pipeline

    retrieval_cfg = retrieval_pipeline.config.setdefault("retrieval", {})
    retrieval_cfg["search_type"] = search_type
    retrieval_pipeline.retriever_configs["search_type"] = search_type

    effective_dense_weight: Optional[float] = None
    if dense_weight is not None:
        effective_dense_weight = min(max(float(dense_weight), 0.0), 1.0)
        dense_cfg = retrieval_cfg.setdefault("dense", {})
        dense_cfg["weight"] = effective_dense_weight
        retrieval_pipeline.retriever_configs.setdefault("dense", {})["weight"] = effective_dense_weight

    reranker = retrieval_pipeline._get_reranker()
    retriever = retrieval_pipeline.retriever
    if retriever is None:
        raise RuntimeError("Dense retriever is disabled or failed to initialize")

    available_tables = _discover_table_names(retriever)
    default_table_name = table_name or retrieval_pipeline.storage_config.get("text_table_name")
    resolved_default_table = _resolve_table_name(default_table_name, available_tables)

    ai_reranker = None
    effective_reranker_top_k = None
    if ai_rerank:
        rr_cfg = retrieval_pipeline.config.setdefault("reranker", {})
        rr_cfg["enabled"] = True
        if reranker_top_k is not None:
            effective_reranker_top_k = max(1, int(reranker_top_k))
            rr_cfg["top_k"] = effective_reranker_top_k
        ai_reranker = retrieval_pipeline._get_ai_reranker()

    total_scored = 0
    total_hits = 0
    reciprocal_rank_sum = 0.0
    per_query: List[Dict[str, Any]] = []

    for row in eval_rows:
        row_id = row.get("id") or "unknown"
        query = row["query"]
        expected_docs = [doc for doc in row.get("expected_evidence_docs", []) if isinstance(doc, str) and doc.strip()]

        requested_table = row.get("table_name") or resolved_default_table
        active_table = _resolve_table_name(requested_table, available_tables)
        if not active_table:
            raise RuntimeError("No table name available. Provide --table-name or include table_name in eval rows.")

        retrieved_docs = retriever.retrieve(
            text_query=query,
            table_name=active_table,
            k=max(k, effective_reranker_top_k or k),
            reranker=reranker,
            search_type=search_type,
        )

        if ai_rerank and ai_reranker and retrieved_docs:
            top_k = effective_reranker_top_k or len(retrieved_docs)
            if hasattr(ai_reranker, "rerank"):
                reranked_docs = ai_reranker.rerank(query, retrieved_docs, top_k=top_k)
            else:
                texts = [doc.get("text", "") for doc in retrieved_docs]
                ranked = ai_reranker.rank(query, texts, top_k=top_k)
                reranked_docs = [retrieved_docs[idx] | {"rerank_score": score} for score, idx in ranked]
            retrieved_docs = reranked_docs

        first_hit_rank = _find_first_match_rank(expected_docs, retrieved_docs, k)
        hit = first_hit_rank is not None
        rr = 1.0 / first_hit_rank if first_hit_rank else 0.0

        total_scored += 1
        total_hits += 1 if hit else 0
        reciprocal_rank_sum += rr

        top_doc_identifiers = [
            _extract_doc_identifiers(doc)
            for doc in retrieved_docs[:k]
        ]

        per_query.append(
            {
                "id": row_id,
                "query": query,
                "expected_evidence_docs": expected_docs,
                "first_hit_rank": first_hit_rank,
                "hit_at_k": hit,
                "reciprocal_rank": rr,
                "top_k_doc_identifiers": top_doc_identifiers,
            }
        )

        print(
            f"[{row_id}] hit@{k}={hit} first_hit_rank={first_hit_rank} "
            f"expected={len(expected_docs)} retrieved={len(retrieved_docs[:k])}"
        )

    citation_hit_rate = (total_hits / total_scored) if total_scored else 0.0
    mrr_at_k = (reciprocal_rank_sum / total_scored) if total_scored else 0.0

    return {
        "summary": {
            "mode": mode,
            "table_name": table_name,
            "resolved_table_name": resolved_default_table,
            "available_table_count": len(available_tables),
            "search_type": search_type,
            "dense_weight": effective_dense_weight,
            "ai_rerank": bool(ai_rerank and ai_reranker is not None),
            "reranker_top_k": effective_reranker_top_k,
            "k": k,
            "total_rows": len(eval_rows),
            "total_scored": total_scored,
            "citation_hit_rate_at_k": round(citation_hit_rate, 4),
            "retrieval_relevance_at_k": round(citation_hit_rate, 4),
            "mrr_at_k": round(mrr_at_k, 4),
        },
        "results": per_query,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval-only evaluation on a JSONL eval set")
    parser.add_argument(
        "--eval-set",
        default="eval/retrieval_eval_set_v1.jsonl",
        help="Path to JSONL evaluation set",
    )
    parser.add_argument(
        "--mode",
        default="default",
        help="RAG agent mode (default|fast)",
    )
    parser.add_argument(
        "--table-name",
        default=None,
        help="LanceDB table name to evaluate against",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Top-k documents to score",
    )
    parser.add_argument(
        "--search-type",
        default="hybrid",
        help="Retrieval search mode (hybrid, vector, fts, etc.)",
    )
    parser.add_argument(
        "--dense-weight",
        type=float,
        default=None,
        help="Dense/vector fusion weight for hybrid retrieval (0.0-1.0)",
    )
    parser.add_argument(
        "--ai-rerank",
        action="store_true",
        help="Apply AI reranker before scoring top-k citations",
    )
    parser.add_argument(
        "--reranker-top-k",
        type=int,
        default=None,
        help="Top-k docs to keep after AI reranking",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output JSON path",
    )
    args = parser.parse_args()

    eval_rows = load_eval_rows(args.eval_set)
    report = evaluate(
        eval_rows,
        mode=args.mode,
        table_name=args.table_name,
        k=max(1, int(args.k)),
        search_type=args.search_type,
        dense_weight=args.dense_weight,
        ai_rerank=args.ai_rerank,
        reranker_top_k=args.reranker_top_k,
    )

    os.makedirs("eval/results", exist_ok=True)
    output_path = args.out
    if not output_path:
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        output_path = os.path.join("eval", "results", f"retrieval_eval_{stamp}.json")

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    summary = report["summary"]
    print("\n=== Retrieval Eval Summary ===")
    print(
        f"rows={summary['total_rows']} k={summary['k']} mode={summary['mode']} "
        f"search_type={summary['search_type']} dense_weight={summary['dense_weight']}"
    )
    print(f"ai_rerank={summary['ai_rerank']} reranker_top_k={summary['reranker_top_k']}")
    print(f"citation_hit_rate@{summary['k']}={summary['citation_hit_rate_at_k']}")
    print(f"retrieval_relevance@{summary['k']}={summary['retrieval_relevance_at_k']}")
    print(f"mrr@{summary['k']}={summary['mrr_at_k']}")
    print(f"report={output_path}")


if __name__ == "__main__":
    main()
