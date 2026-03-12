#!/usr/bin/env python3
"""Check retrieval and answer-quality reports against release gates."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Tuple


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _summary(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else {}


def check_gates(
    *,
    baseline_retrieval: Dict[str, Any],
    candidate_retrieval: Dict[str, Any],
    answer_quality: Dict[str, Any],
    min_retrieval_relevance_delta: float,
    min_grounded_rate: float,
    min_citation_presence_rate: float,
    max_latency_regression_pct: float,
) -> Tuple[bool, Dict[str, Any]]:
    base = _summary(baseline_retrieval)
    cand = _summary(candidate_retrieval)
    quality = _summary(answer_quality)

    base_rel = float(base.get("retrieval_relevance_at_k", 0.0))
    cand_rel = float(cand.get("retrieval_relevance_at_k", 0.0))
    rel_delta = cand_rel - base_rel

    base_p95 = float(base.get("latency_ms_p95", 0.0))
    cand_p95 = float(cand.get("latency_ms_p95", 0.0))
    latency_regression_pct = 0.0
    if base_p95 > 0:
        latency_regression_pct = ((cand_p95 - base_p95) / base_p95) * 100.0

    grounded_rate = float(quality.get("grounded_rate", 0.0))
    citation_presence_rate = float(quality.get("citation_presence_rate", 0.0))

    checks: List[Dict[str, Any]] = [
        {
            "name": "retrieval_relevance_delta",
            "actual": round(rel_delta, 4),
            "threshold": min_retrieval_relevance_delta,
            "passed": rel_delta >= min_retrieval_relevance_delta,
        },
        {
            "name": "latency_regression_pct",
            "actual": round(latency_regression_pct, 2),
            "threshold": max_latency_regression_pct,
            "passed": latency_regression_pct <= max_latency_regression_pct,
        },
        {
            "name": "grounded_rate",
            "actual": round(grounded_rate, 4),
            "threshold": min_grounded_rate,
            "passed": grounded_rate >= min_grounded_rate,
        },
        {
            "name": "citation_presence_rate",
            "actual": round(citation_presence_rate, 4),
            "threshold": min_citation_presence_rate,
            "passed": citation_presence_rate >= min_citation_presence_rate,
        },
    ]

    passed = all(bool(check["passed"]) for check in checks)
    return passed, {
        "passed": passed,
        "checks": checks,
        "metrics": {
            "baseline_retrieval_relevance": round(base_rel, 4),
            "candidate_retrieval_relevance": round(cand_rel, 4),
            "baseline_latency_ms_p95": round(base_p95, 2),
            "candidate_latency_ms_p95": round(cand_p95, 2),
            "grounded_rate": round(grounded_rate, 4),
            "citation_presence_rate": round(citation_presence_rate, 4),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check quality/performance gates for RAG promotion")
    parser.add_argument("--baseline-retrieval", required=True, help="Baseline retrieval eval JSON report")
    parser.add_argument("--candidate-retrieval", required=True, help="Candidate retrieval eval JSON report")
    parser.add_argument("--answer-quality", required=True, help="Answer quality eval JSON report")
    parser.add_argument("--min-retrieval-relevance-delta", type=float, default=0.05)
    parser.add_argument("--min-grounded-rate", type=float, default=0.8)
    parser.add_argument("--min-citation-presence-rate", type=float, default=0.8)
    parser.add_argument("--max-latency-regression-pct", type=float, default=15.0)
    parser.add_argument("--out", default=None, help="Optional path to write gate summary JSON")
    args = parser.parse_args()

    baseline_retrieval = _load_json(args.baseline_retrieval)
    candidate_retrieval = _load_json(args.candidate_retrieval)
    answer_quality = _load_json(args.answer_quality)

    passed, report = check_gates(
        baseline_retrieval=baseline_retrieval,
        candidate_retrieval=candidate_retrieval,
        answer_quality=answer_quality,
        min_retrieval_relevance_delta=args.min_retrieval_relevance_delta,
        min_grounded_rate=args.min_grounded_rate,
        min_citation_presence_rate=args.min_citation_presence_rate,
        max_latency_regression_pct=args.max_latency_regression_pct,
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)

    print("=== Gate Check Summary ===")
    for check in report["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"{status} {check['name']}: actual={check['actual']} threshold={check['threshold']}")

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
