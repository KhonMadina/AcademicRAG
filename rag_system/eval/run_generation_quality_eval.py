#!/usr/bin/env python3
"""Run answer-quality evaluation with verifier and citation checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Sequence

from rag_system.eval.run_retrieval_eval import _percentile, load_eval_rows
from rag_system.main import get_agent

_CITATION_PATTERN = re.compile(r"\[S(\d+)\]")
_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in _WORD_PATTERN.findall(text or "")]


def _note_coverage(answer: str, expected_notes: str) -> float:
    expected_tokens = set(_tokenize(expected_notes))
    if not expected_tokens:
        return 0.0
    answer_tokens = set(_tokenize(answer))
    overlap = len(expected_tokens.intersection(answer_tokens))
    return overlap / len(expected_tokens)


def evaluate_answer_quality(
    eval_rows: Sequence[Dict[str, Any]],
    *,
    mode: str,
    table_name: str | None,
    verify: bool,
    retrieval_k: int | None = None,
    search_type: str | None = None,
    dense_weight: float | None = None,
    ai_rerank: bool | None = None,
    reranker_top_k: int | None = None,
) -> Dict[str, Any]:
    agent = get_agent(mode)

    per_query: List[Dict[str, Any]] = []
    latencies_ms: List[float] = []
    grounded_count = 0
    with_citation_count = 0
    confidence_scores: List[float] = []
    note_coverages: List[float] = []

    for row in eval_rows:
        row_id = row.get("id", "unknown")
        query = str(row.get("query", "")).strip()
        expected_notes = str(row.get("expected_answer_notes", "")).strip()

        started = time.perf_counter()
        result = agent.run(
            query,
            table_name=table_name or row.get("table_name"),
            verify=verify,
            retrieval_k=retrieval_k,
            search_type=search_type,
            dense_weight=dense_weight,
            ai_rerank=ai_rerank,
            reranker_top_k=reranker_top_k,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        latencies_ms.append(latency_ms)

        answer = str(result.get("answer", "") or "")
        verification = result.get("verification") or {}
        is_grounded = verification.get("is_grounded")
        confidence = verification.get("confidence_score")

        citations = sorted({int(match) for match in _CITATION_PATTERN.findall(answer)})
        has_citation = len(citations) > 0
        with_citation_count += 1 if has_citation else 0

        if isinstance(is_grounded, bool) and is_grounded:
            grounded_count += 1
        if isinstance(confidence, (int, float)):
            confidence_scores.append(float(confidence))

        note_coverage = _note_coverage(answer, expected_notes) if expected_notes else 0.0
        if expected_notes:
            note_coverages.append(note_coverage)

        per_query.append(
            {
                "id": row_id,
                "query": query,
                "latency_ms": round(latency_ms, 2),
                "has_citation": has_citation,
                "citation_ids": citations,
                "verification": {
                    "enabled": bool(verification.get("enabled")),
                    "is_grounded": is_grounded,
                    "verdict": verification.get("verdict"),
                    "confidence_score": confidence,
                },
                "expected_answer_notes": expected_notes,
                "note_coverage": round(note_coverage, 4) if expected_notes else None,
            }
        )

        print(
            f"[{row_id}] grounded={is_grounded} confidence={confidence} "
            f"citations={len(citations)} latency_ms={latency_ms:.1f}"
        )

    row_count = len(per_query)
    confidence_mean = (sum(confidence_scores) / len(confidence_scores)) if confidence_scores else 0.0
    note_coverage_mean = (sum(note_coverages) / len(note_coverages)) if note_coverages else 0.0

    return {
        "summary": {
            "mode": mode,
            "table_name": table_name,
            "total_rows": row_count,
            "grounded_rate": round((grounded_count / row_count) if row_count else 0.0, 4),
            "citation_presence_rate": round((with_citation_count / row_count) if row_count else 0.0, 4),
            "confidence_mean": round(confidence_mean, 2),
            "note_coverage_mean": round(note_coverage_mean, 4),
            "latency_ms_mean": round((sum(latencies_ms) / len(latencies_ms)) if latencies_ms else 0.0, 2),
            "latency_ms_p50": round(_percentile(latencies_ms, 50), 2),
            "latency_ms_p95": round(_percentile(latencies_ms, 95), 2),
            "latency_ms_max": round(max(latencies_ms) if latencies_ms else 0.0, 2),
        },
        "results": per_query,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run answer-quality evaluation")
    parser.add_argument("--eval-set", default="eval/retrieval_eval_set_v1.jsonl", help="Path to eval JSONL")
    parser.add_argument("--mode", default="default", help="Agent mode")
    parser.add_argument("--table-name", default=None, help="Optional table override")
    parser.add_argument("--verify", action="store_true", help="Enable verifier during quality evaluation")
    parser.add_argument("--retrieval-k", type=int, default=None)
    parser.add_argument("--search-type", default=None)
    parser.add_argument("--dense-weight", type=float, default=None)
    parser.add_argument("--ai-rerank", action="store_true", help="Force AI rerank on")
    parser.add_argument("--no-ai-rerank", action="store_true", help="Force AI rerank off")
    parser.add_argument("--reranker-top-k", type=int, default=None)
    parser.add_argument("--out", default=None, help="Output JSON report path")
    args = parser.parse_args()

    eval_rows = load_eval_rows(args.eval_set)
    ai_rerank = None
    if args.ai_rerank and args.no_ai_rerank:
        raise ValueError("Cannot set both --ai-rerank and --no-ai-rerank")
    if args.ai_rerank:
        ai_rerank = True
    if args.no_ai_rerank:
        ai_rerank = False

    report = evaluate_answer_quality(
        eval_rows,
        mode=args.mode,
        table_name=args.table_name,
        verify=args.verify,
        retrieval_k=args.retrieval_k,
        search_type=args.search_type,
        dense_weight=args.dense_weight,
        ai_rerank=ai_rerank,
        reranker_top_k=args.reranker_top_k,
    )

    os.makedirs("eval/results", exist_ok=True)
    output_path = args.out
    if not output_path:
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        output_path = os.path.join("eval", "results", f"answer_quality_eval_{stamp}.json")

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    summary = report["summary"]
    print("\n=== Answer Quality Summary ===")
    print(
        f"rows={summary['total_rows']} grounded_rate={summary['grounded_rate']} "
        f"citation_presence_rate={summary['citation_presence_rate']} "
        f"confidence_mean={summary['confidence_mean']}"
    )
    print(
        f"latency_ms mean={summary['latency_ms_mean']} p50={summary['latency_ms_p50']} "
        f"p95={summary['latency_ms_p95']} max={summary['latency_ms_max']}"
    )
    print(f"note_coverage_mean={summary['note_coverage_mean']}")
    print(f"report={output_path}")


if __name__ == "__main__":
    main()
