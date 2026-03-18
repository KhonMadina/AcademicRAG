#!/usr/bin/env python3
"""Execute the full RAG tuning/improvement plan end-to-end."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import Any, Dict

from rag_system.eval.check_quality_perf_gates import check_gates
from rag_system.eval.run_generation_quality_eval import evaluate_answer_quality
from rag_system.eval.run_retrieval_eval import evaluate, load_eval_rows
from rag_system.eval.tune_retrieval_params import (
    _candidate_grid,
    _default_baseline,
    _parse_csv_floats,
    _parse_csv_ints,
    _parse_csv_text,
    tune,
)


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full RAG tuning and quality/performance improvement plan")
    parser.add_argument("--eval-set", default="eval/retrieval_eval_set_v1.jsonl")
    parser.add_argument("--mode", default="default")
    parser.add_argument("--table-name", default=None)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--search-types", default="hybrid,vector,fts")
    parser.add_argument("--dense-weights", default="0.4,0.5,0.6,0.7,0.8")
    parser.add_argument("--ai-rerank", action="store_true")
    parser.add_argument("--reranker-top-k-values", default="5,10,15")
    parser.add_argument("--max-latency-regression-pct", type=float, default=15.0)
    parser.add_argument("--min-retrieval-relevance-delta", type=float, default=0.05)
    parser.add_argument("--min-grounded-rate", type=float, default=0.8)
    parser.add_argument("--min-citation-presence-rate", type=float, default=0.8)
    parser.add_argument("--verify", action="store_true", help="Enable verifier in answer-quality evaluation")
    parser.add_argument("--out-dir", default="eval/results")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    print("\n[Step 1/6] Baseline retrieval evaluation")
    eval_rows = load_eval_rows(args.eval_set)
    baseline_cfg = _default_baseline(args.mode, args.ai_rerank)
    baseline_report = evaluate(
        eval_rows,
        mode=args.mode,
        table_name=args.table_name,
        k=max(1, int(args.k)),
        search_type=baseline_cfg.search_type,
        dense_weight=baseline_cfg.dense_weight,
        ai_rerank=baseline_cfg.ai_rerank,
        reranker_top_k=baseline_cfg.reranker_top_k,
    )
    baseline_path = os.path.join(args.out_dir, f"plan_step1_baseline_{stamp}.json")
    _write_json(baseline_path, baseline_report)

    print("\n[Step 2/6] Retrieval tuning sweep")
    search_types = _parse_csv_text(args.search_types)
    dense_weights = _parse_csv_floats(args.dense_weights)
    reranker_top_k_values = _parse_csv_ints(args.reranker_top_k_values)
    candidates = _candidate_grid(
        search_types,
        dense_weights,
        ai_rerank=args.ai_rerank,
        reranker_top_k_values=reranker_top_k_values,
    )
    tuning_report = tune(
        eval_rows,
        mode=args.mode,
        table_name=args.table_name,
        k=max(1, int(args.k)),
        baseline=baseline_cfg,
        candidates=candidates,
        max_latency_regression_pct=args.max_latency_regression_pct,
    )
    tuning_path = os.path.join(args.out_dir, f"plan_step2_tuning_{stamp}.json")
    _write_json(tuning_path, tuning_report)

    best = tuning_report["best"]

    print("\n[Step 3/6] Candidate retrieval validation")
    candidate_retrieval_report = evaluate(
        eval_rows,
        mode=args.mode,
        table_name=args.table_name,
        k=max(1, int(args.k)),
        search_type=str(best.get("search_type", "hybrid")),
        dense_weight=best.get("dense_weight"),
        ai_rerank=bool(best.get("ai_rerank", False)),
        reranker_top_k=best.get("reranker_top_k"),
    )
    candidate_retrieval_path = os.path.join(args.out_dir, f"plan_step3_candidate_retrieval_{stamp}.json")
    _write_json(candidate_retrieval_path, candidate_retrieval_report)

    print("\n[Step 4/6] Answer quality evaluation")
    answer_quality_report = evaluate_answer_quality(
        eval_rows,
        mode=args.mode,
        table_name=args.table_name,
        verify=args.verify,
        retrieval_k=max(1, int(args.k)),
        search_type=str(best.get("search_type", "hybrid")),
        dense_weight=(float(best.get("dense_weight")) if best.get("dense_weight") is not None else None),
        ai_rerank=bool(best.get("ai_rerank", False)),
        reranker_top_k=(int(best.get("reranker_top_k")) if best.get("reranker_top_k") is not None else None),
    )
    answer_quality_path = os.path.join(args.out_dir, f"plan_step4_answer_quality_{stamp}.json")
    _write_json(answer_quality_path, answer_quality_report)

    print("\n[Step 5/6] Gate checks (quality + performance)")
    passed, gate_report = check_gates(
        baseline_retrieval=baseline_report,
        candidate_retrieval=candidate_retrieval_report,
        answer_quality=answer_quality_report,
        min_retrieval_relevance_delta=args.min_retrieval_relevance_delta,
        min_grounded_rate=args.min_grounded_rate,
        min_citation_presence_rate=args.min_citation_presence_rate,
        max_latency_regression_pct=args.max_latency_regression_pct,
    )
    gate_path = os.path.join(args.out_dir, f"plan_step5_gate_check_{stamp}.json")
    _write_json(gate_path, gate_report)

    print("\n[Step 6/6] Final summary")
    final_summary = {
        "passed": passed,
        "artifacts": {
            "baseline_retrieval": baseline_path,
            "tuning": tuning_path,
            "candidate_retrieval": candidate_retrieval_path,
            "answer_quality": answer_quality_path,
            "gate_check": gate_path,
        },
        "best_candidate": best,
        "improvement": tuning_report.get("improvement", {}),
        "gate_report": gate_report,
    }
    final_path = os.path.join(args.out_dir, f"plan_final_summary_{stamp}.json")
    _write_json(final_path, final_summary)

    print("=== Plan Execution Complete ===")
    print(f"passed={passed}")
    print(f"summary={final_path}")

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
