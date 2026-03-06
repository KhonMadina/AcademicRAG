#!/usr/bin/env python3
"""Grid-search retrieval parameters against the versioned eval set."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from rag_system.eval.run_retrieval_eval import evaluate, load_eval_rows
from rag_system.main import get_agent


def _parse_csv_floats(raw: str) -> List[float]:
    values: List[float] = []
    for part in (raw or "").split(","):
        text = part.strip()
        if not text:
            continue
        values.append(float(text))
    deduped = sorted({min(max(v, 0.0), 1.0) for v in values})
    if not deduped:
        raise ValueError("At least one float value is required")
    return deduped


def _parse_csv_text(raw: str) -> List[str]:
    values = [part.strip().lower() for part in (raw or "").split(",") if part.strip()]
    deduped = sorted(set(values))
    if not deduped:
        raise ValueError("At least one text value is required")
    return deduped


def _parse_csv_ints(raw: str) -> List[int]:
    values: List[int] = []
    for part in (raw or "").split(","):
        text = part.strip()
        if not text:
            continue
        values.append(max(1, int(text)))
    deduped = sorted(set(values))
    if not deduped:
        raise ValueError("At least one integer value is required")
    return deduped


def _score_key(candidate: Dict[str, Any]) -> tuple:
    return (
        float(candidate.get("retrieval_relevance_at_k", 0.0)),
        float(candidate.get("mrr_at_k", 0.0)),
        -float(candidate.get("dense_weight") if candidate.get("dense_weight") is not None else 0.5),
    )


@dataclass
class CandidateConfig:
    search_type: str
    dense_weight: float
    ai_rerank: bool
    reranker_top_k: Optional[int]


def _default_baseline(mode: str, ai_rerank_enabled: bool) -> CandidateConfig:
    agent = get_agent(mode)
    retrieval_cfg = agent.retrieval_pipeline.config.get("retrieval", {})
    reranker_cfg = agent.retrieval_pipeline.config.get("reranker", {})
    return CandidateConfig(
        search_type=str(retrieval_cfg.get("search_type", "hybrid")).lower(),
        dense_weight=float(retrieval_cfg.get("dense", {}).get("weight", 0.5)),
        ai_rerank=bool(ai_rerank_enabled),
        reranker_top_k=reranker_cfg.get("top_k") if ai_rerank_enabled else None,
    )


def _candidate_grid(
    search_types: Sequence[str],
    dense_weights: Sequence[float],
    ai_rerank: bool,
    reranker_top_k_values: Sequence[int],
) -> List[CandidateConfig]:
    candidates: List[CandidateConfig] = []
    if ai_rerank:
        for search_type in search_types:
            for dense_weight in dense_weights:
                for top_k in reranker_top_k_values:
                    candidates.append(
                        CandidateConfig(
                            search_type=search_type,
                            dense_weight=float(dense_weight),
                            ai_rerank=True,
                            reranker_top_k=max(1, int(top_k)),
                        )
                    )
    else:
        for search_type in search_types:
            for dense_weight in dense_weights:
                candidates.append(
                    CandidateConfig(
                        search_type=search_type,
                        dense_weight=float(dense_weight),
                        ai_rerank=False,
                        reranker_top_k=None,
                    )
                )
    return candidates


def tune(
    eval_rows: Sequence[Dict[str, Any]],
    *,
    mode: str,
    table_name: Optional[str],
    k: int,
    baseline: CandidateConfig,
    candidates: Sequence[CandidateConfig],
) -> Dict[str, Any]:
    baseline_report = evaluate(
        eval_rows,
        mode=mode,
        table_name=table_name,
        k=k,
        search_type=baseline.search_type,
        dense_weight=baseline.dense_weight,
        ai_rerank=baseline.ai_rerank,
        reranker_top_k=baseline.reranker_top_k,
    )
    baseline_summary = baseline_report["summary"]

    candidate_summaries: List[Dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        print(
            f"\n[{index}/{len(candidates)}] search_type={candidate.search_type} "
            f"dense_weight={candidate.dense_weight} ai_rerank={candidate.ai_rerank} "
            f"reranker_top_k={candidate.reranker_top_k}"
        )
        report = evaluate(
            eval_rows,
            mode=mode,
            table_name=table_name,
            k=k,
            search_type=candidate.search_type,
            dense_weight=candidate.dense_weight,
            ai_rerank=candidate.ai_rerank,
            reranker_top_k=candidate.reranker_top_k,
        )
        candidate_summaries.append(report["summary"])

    if not candidate_summaries:
        raise RuntimeError("No candidate summaries generated")

    best_summary = max(candidate_summaries, key=_score_key)

    baseline_rel = float(baseline_summary.get("retrieval_relevance_at_k", 0.0))
    best_rel = float(best_summary.get("retrieval_relevance_at_k", 0.0))
    baseline_mrr = float(baseline_summary.get("mrr_at_k", 0.0))
    best_mrr = float(best_summary.get("mrr_at_k", 0.0))

    return {
        "baseline": baseline_summary,
        "best": best_summary,
        "improvement": {
            "retrieval_relevance_delta": round(best_rel - baseline_rel, 4),
            "mrr_delta": round(best_mrr - baseline_mrr, 4),
            "improved": (best_rel > baseline_rel) or (best_rel == baseline_rel and best_mrr > baseline_mrr),
        },
        "candidates": candidate_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune retrieval parameters via eval-set grid search")
    parser.add_argument("--eval-set", default="eval/retrieval_eval_set_v1.jsonl", help="JSONL eval set path")
    parser.add_argument("--mode", default="default", help="Agent mode")
    parser.add_argument("--table-name", default=None, help="LanceDB table name")
    parser.add_argument("--k", type=int, default=5, help="Top-k used for scoring")
    parser.add_argument("--search-types", default="hybrid,vector,fts", help="Comma-separated search modes")
    parser.add_argument("--dense-weights", default="0.4,0.5,0.6,0.7,0.8", help="Comma-separated dense weights")
    parser.add_argument("--ai-rerank", action="store_true", help="Include AI rerank in candidate configs")
    parser.add_argument(
        "--reranker-top-k-values",
        default="5,10,15",
        help="Comma-separated top-k values for AI rerank (used only with --ai-rerank)",
    )
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()

    eval_rows = load_eval_rows(args.eval_set)
    search_types = _parse_csv_text(args.search_types)
    dense_weights = _parse_csv_floats(args.dense_weights)
    reranker_top_k_values = _parse_csv_ints(args.reranker_top_k_values)

    baseline = _default_baseline(args.mode, args.ai_rerank)
    candidates = _candidate_grid(
        search_types,
        dense_weights,
        ai_rerank=args.ai_rerank,
        reranker_top_k_values=reranker_top_k_values,
    )

    report = tune(
        eval_rows,
        mode=args.mode,
        table_name=args.table_name,
        k=max(1, int(args.k)),
        baseline=baseline,
        candidates=candidates,
    )

    os.makedirs("eval/results", exist_ok=True)
    output_path = args.out
    if not output_path:
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        output_path = os.path.join("eval", "results", f"retrieval_tuning_{stamp}.json")

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    baseline_summary = report["baseline"]
    best_summary = report["best"]
    improvement = report["improvement"]

    print("\n=== Retrieval Tuning Summary ===")
    print(
        "baseline: "
        f"search_type={baseline_summary.get('search_type')} "
        f"dense_weight={baseline_summary.get('dense_weight')} "
        f"rel={baseline_summary.get('retrieval_relevance_at_k')} "
        f"mrr={baseline_summary.get('mrr_at_k')}"
    )
    print(
        "best: "
        f"search_type={best_summary.get('search_type')} "
        f"dense_weight={best_summary.get('dense_weight')} "
        f"ai_rerank={best_summary.get('ai_rerank')} "
        f"reranker_top_k={best_summary.get('reranker_top_k')} "
        f"rel={best_summary.get('retrieval_relevance_at_k')} "
        f"mrr={best_summary.get('mrr_at_k')}"
    )
    print(
        f"delta: rel={improvement.get('retrieval_relevance_delta')} "
        f"mrr={improvement.get('mrr_delta')} improved={improvement.get('improved')}"
    )
    print(f"report={output_path}")


if __name__ == "__main__":
    main()
