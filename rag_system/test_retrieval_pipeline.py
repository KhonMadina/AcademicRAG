#!/usr/bin/env python3
"""Smoke tests for retrieval pipeline behavior and response contracts."""

import unittest
import numpy as np

from rag_system.pipelines.retrieval_pipeline import RetrievalPipeline


class DummyOllamaClient:
    def stream_completion(self, model: str, prompt: str):
        yield "dummy"


class ScaffoldEchoOllamaClient:
    def stream_completion(self, model: str, prompt: str):
        yield "Answer:\n"
        yield "CJCC focuses on student exchange programs [S1].\n\n"
        yield "Retrieved Snippets\n"
        yield "[S1] source text"


class FakeDenseRetriever:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.fusion_config = {}
        self.calls = []

    def retrieve(self, text_query, table_name, k, reranker=None, search_type=None):
        self.calls.append(
            {
                "text_query": text_query,
                "table_name": table_name,
                "k": k,
                "search_type": search_type,
            }
        )
        return list(self.docs)


class RetrievalPipelineSmokeTests(unittest.TestCase):
    def _make_pipeline(self):
        config = {
            "storage": {
                "db_path": "./lancedb",
                "text_table_name": "smoke_table",
                "image_table_name": "smoke_images",
            },
            "retrieval": {
                "search_type": "hybrid",
                "dense": {"enabled": True, "weight": 0.7},
                "bm25": {"enabled": False},
            },
            "reranker": {"enabled": False},
            "retrieval_k": 3,
            "context_window_size": 0,
        }
        ollama_config = {
            "host": "http://localhost:11434",
            "generation_model": "gemma3:12b-cloud",
        }
        return RetrievalPipeline(config, DummyOllamaClient(), ollama_config)

    def test_empty_retrieval_returns_empty_sources(self):
        pipeline = self._make_pipeline()
        fake_retriever = FakeDenseRetriever(docs=[])

        pipeline._get_dense_retriever = lambda: fake_retriever

        result = pipeline.run("What is in this index?", table_name="smoke_empty")

        self.assertEqual(result["answer"], "I could not find an answer in the documents.")
        self.assertEqual(result["source_documents"], [])
        self.assertEqual(len(fake_retriever.calls), 1)
        self.assertEqual(fake_retriever.calls[0]["table_name"], "smoke_empty")
        self.assertEqual(fake_retriever.calls[0]["k"], 3)

    def test_indexed_retrieval_returns_sources_and_answer(self):
        pipeline = self._make_pipeline()

        docs = [
            {
                "chunk_id": "c1",
                "document_id": "doc-1",
                "chunk_index": 0,
                "text": "AcademicRAG is a private document intelligence platform.",
                "score": 0.99,
                "vector": [0.1, 0.2],
                "_distance": 0.12,
                "_fused_score": 0.88,
            },
            {
                "chunk_id": "c2",
                "document_id": "doc-1",
                "chunk_index": 1,
                "text": "It supports hybrid retrieval and verification.",
                "score": float("nan"),
            },
        ]
        fake_retriever = FakeDenseRetriever(docs=docs)

        pipeline._get_dense_retriever = lambda: fake_retriever
        pipeline._synthesize_final_answer = lambda query, facts, event_callback=None: "Synthetic smoke answer"

        result = pipeline.run("What is AcademicRAG?", table_name="smoke_table")

        self.assertEqual(result["answer"], "Synthetic smoke answer")
        self.assertGreaterEqual(len(result["source_documents"]), 1)

        first = result["source_documents"][0]
        self.assertIn("text", first)
        self.assertNotIn("vector", first)
        self.assertNotIn("_distance", first)
        self.assertNotIn("_fused_score", first)

        second = result["source_documents"][1]
        self.assertIsNone(second.get("score"))

    def test_diagnostics_returns_pre_and_post_lists(self):
        pipeline = self._make_pipeline()

        docs = [
            {
                "chunk_id": "c1",
                "document_id": "doc-1",
                "chunk_index": 0,
                "text": "Alpha",
                "score": 0.91,
            },
            {
                "chunk_id": "c2",
                "document_id": "doc-2",
                "chunk_index": 1,
                "text": "Beta",
                "score": 0.55,
            },
        ]
        fake_retriever = FakeDenseRetriever(docs=docs)

        pipeline._get_dense_retriever = lambda: fake_retriever
        pipeline._get_reranker = lambda: None
        pipeline._get_ai_reranker = lambda: None

        result = pipeline.diagnose_retrieval(
            query="What is this?",
            table_name="smoke_table",
            retrieval_k=2,
            pre_rerank_k=2,
            post_rerank_k=2,
            apply_ai_rerank=False,
        )

        self.assertEqual(result["query"], "What is this?")
        self.assertEqual(result["table_name"], "smoke_table")
        self.assertEqual(len(result["retrieval"]["pre_rerank"]), 2)
        self.assertEqual(len(result["retrieval"]["post_rerank"]), 2)
        self.assertFalse(result["retrieval"]["ai_rerank_applied"])

    def test_diagnostics_applies_rank_style_reranker(self):
        pipeline = self._make_pipeline()

        docs = [
            {
                "chunk_id": "c1",
                "document_id": "doc-1",
                "chunk_index": 0,
                "text": "Alpha",
                "score": 0.91,
            },
            {
                "chunk_id": "c2",
                "document_id": "doc-2",
                "chunk_index": 1,
                "text": "Beta",
                "score": 0.55,
            },
        ]
        fake_retriever = FakeDenseRetriever(docs=docs)

        class FakeRanker:
            def rank(self, query, docs, top_k=1):
                return [(0.99, 1), (0.70, 0)][:top_k]

        pipeline._get_dense_retriever = lambda: fake_retriever
        pipeline._get_reranker = lambda: None
        pipeline._get_ai_reranker = lambda: FakeRanker()
        pipeline.config["reranker"]["enabled"] = True
        pipeline.config["reranker"]["strategy"] = "qwen"

        result = pipeline.diagnose_retrieval(
            query="Which chunk ranks higher?",
            table_name="smoke_table",
            retrieval_k=2,
            pre_rerank_k=2,
            post_rerank_k=2,
            apply_ai_rerank=True,
        )

        post_docs = result["retrieval"]["post_rerank"]
        self.assertTrue(result["retrieval"]["ai_rerank_applied"])
        self.assertEqual(post_docs[0]["chunk_id"], "c2")
        self.assertEqual(post_docs[0]["rerank_score"], 0.99)

    def test_synthesize_strips_prompt_scaffolding(self):
        pipeline = self._make_pipeline()
        pipeline.ollama_client = ScaffoldEchoOllamaClient()

        answer = pipeline._synthesize_final_answer(
            "What does CJCC focus on?",
            "[S1] CJCC focuses on student exchange programs.",
        )

        self.assertEqual(answer, "CJCC focuses on student exchange programs [S1].")


if __name__ == "__main__":
    unittest.main(verbosity=2)
