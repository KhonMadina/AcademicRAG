#!/usr/bin/env python3
"""Unit tests for retrieval parameter tuner helper functions."""

import unittest

from rag_system.eval.tune_retrieval_params import (
    _candidate_grid,
    _parse_csv_floats,
    _parse_csv_ints,
    _parse_csv_text,
    _score_key,
)


class RetrievalTunerTests(unittest.TestCase):
    def test_parse_csv_floats_clamps_and_dedupes(self):
        values = _parse_csv_floats("0.7, 1.2, -0.1, 0.7")
        self.assertEqual(values, [0.0, 0.7, 1.0])

    def test_parse_csv_text_normalizes(self):
        values = _parse_csv_text("Hybrid, vector, hybrid, FTS")
        self.assertEqual(values, ["fts", "hybrid", "vector"])

    def test_parse_csv_ints_normalizes(self):
        values = _parse_csv_ints("10, 5, 0, 10")
        self.assertEqual(values, [1, 5, 10])

    def test_candidate_grid_without_ai_rerank(self):
        candidates = _candidate_grid(["hybrid", "vector"], [0.5, 0.7], False, [5, 10])
        self.assertEqual(len(candidates), 4)
        self.assertTrue(all(candidate.ai_rerank is False for candidate in candidates))
        self.assertTrue(all(candidate.reranker_top_k is None for candidate in candidates))

    def test_candidate_grid_with_ai_rerank(self):
        candidates = _candidate_grid(["hybrid"], [0.6], True, [5, 10])
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(candidate.ai_rerank is True for candidate in candidates))
        self.assertEqual({candidate.reranker_top_k for candidate in candidates}, {5, 10})

    def test_score_key_prefers_relevance_then_mrr(self):
        a = {
            "retrieval_relevance_at_k": 0.8,
            "mrr_at_k": 0.45,
            "dense_weight": 0.7,
        }
        b = {
            "retrieval_relevance_at_k": 0.8,
            "mrr_at_k": 0.5,
            "dense_weight": 0.8,
        }
        self.assertLess(_score_key(a), _score_key(b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
