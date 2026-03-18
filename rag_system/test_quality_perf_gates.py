#!/usr/bin/env python3
"""Tests for quality/performance gate checks."""

import unittest

from rag_system.eval.check_quality_perf_gates import check_gates


class QualityPerfGateTests(unittest.TestCase):
    def test_gate_passes_when_all_thresholds_met(self):
        baseline = {
            "summary": {
                "retrieval_relevance_at_k": 0.6,
                "latency_ms_p95": 100.0,
            }
        }
        candidate = {
            "summary": {
                "retrieval_relevance_at_k": 0.7,
                "latency_ms_p95": 110.0,
            }
        }
        answer_quality = {
            "summary": {
                "grounded_rate": 0.85,
                "citation_presence_rate": 0.9,
            }
        }

        passed, report = check_gates(
            baseline_retrieval=baseline,
            candidate_retrieval=candidate,
            answer_quality=answer_quality,
            min_retrieval_relevance_delta=0.05,
            min_grounded_rate=0.8,
            min_citation_presence_rate=0.8,
            max_latency_regression_pct=15.0,
        )

        self.assertTrue(passed)
        self.assertTrue(all(check["passed"] for check in report["checks"]))

    def test_gate_fails_on_latency_regression(self):
        baseline = {
            "summary": {
                "retrieval_relevance_at_k": 0.6,
                "latency_ms_p95": 100.0,
            }
        }
        candidate = {
            "summary": {
                "retrieval_relevance_at_k": 0.7,
                "latency_ms_p95": 130.0,
            }
        }
        answer_quality = {
            "summary": {
                "grounded_rate": 0.9,
                "citation_presence_rate": 0.95,
            }
        }

        passed, report = check_gates(
            baseline_retrieval=baseline,
            candidate_retrieval=candidate,
            answer_quality=answer_quality,
            min_retrieval_relevance_delta=0.05,
            min_grounded_rate=0.8,
            min_citation_presence_rate=0.8,
            max_latency_regression_pct=15.0,
        )

        self.assertFalse(passed)
        latency_check = next(check for check in report["checks"] if check["name"] == "latency_regression_pct")
        self.assertFalse(latency_check["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
