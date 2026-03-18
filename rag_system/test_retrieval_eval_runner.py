#!/usr/bin/env python3
"""Unit tests for retrieval evaluation matching/scoring helpers."""

import unittest

from rag_system.eval.run_retrieval_eval import (
    _extract_doc_identifiers,
    _find_first_match_rank,
    _match_expected_to_retrieved,
    _resolve_table_name,
)


class RetrievalEvalRunnerTests(unittest.TestCase):
    def test_identifier_matching_accepts_path_and_stem(self):
        self.assertTrue(
            _match_expected_to_retrieved(
                "Documentation/architecture_overview.md",
                "architecture_overview",
            )
        )
        self.assertTrue(
            _match_expected_to_retrieved(
                "architecture-overview.md",
                "docs/architecture_overview.md",
            )
        )

    def test_extract_doc_identifiers_reads_metadata_and_doc_fields(self):
        doc = {
            "document_id": "Documentation/retrieval_pipeline.md",
            "metadata": {
                "title": "Retrieval Pipeline",
                "filename": "retrieval_pipeline.md",
            },
        }
        identifiers = _extract_doc_identifiers(doc)
        self.assertIn("documentation/retrieval pipeline.md", identifiers)
        self.assertIn("retrieval pipeline", identifiers)

    def test_first_match_rank_detects_expected_doc_in_top_k(self):
        docs = [
            {"document_id": "random_doc.md", "metadata": {}},
            {"document_id": "Documentation/api_reference.md", "metadata": {}},
            {"document_id": "Documentation/system_overview.md", "metadata": {}},
        ]
        rank = _find_first_match_rank(["api_reference.md"], docs, k=3)
        self.assertEqual(rank, 2)

    def test_first_match_rank_returns_none_when_no_matches(self):
        docs = [
            {"document_id": "a.md", "metadata": {}},
            {"document_id": "b.md", "metadata": {}},
        ]
        rank = _find_first_match_rank(["missing.md"], docs, k=2)
        self.assertIsNone(rank)

    def test_resolve_table_name_prefers_exact_match(self):
        resolved = _resolve_table_name("text_pages_v3", ["text_pages_v2", "text_pages_v3"])
        self.assertEqual(resolved, "text_pages_v3")

    def test_resolve_table_name_falls_back_to_prefix(self):
        resolved = _resolve_table_name("text_pages_v3", ["text_pages_abc123", "other_table"])
        self.assertEqual(resolved, "text_pages_abc123")


if __name__ == "__main__":
    unittest.main(verbosity=2)
