#!/usr/bin/env python3
"""Unit tests for memory-aware indexing controls."""

import unittest

from rag_system.pipelines.indexing_pipeline import IndexingPipeline


class IndexingMemoryControlsTests(unittest.TestCase):
    def _make_pipeline_like(self):
        pipeline = IndexingPipeline.__new__(IndexingPipeline)
        pipeline.min_safe_embedding_batch = 4
        pipeline.max_safe_embedding_batch = 24
        pipeline.min_safe_enrichment_batch = 2
        pipeline.max_safe_enrichment_batch = 24
        pipeline.low_memory_threshold_mb = 3072
        pipeline.target_memory_budget_mb = 1024.0
        pipeline.embedding_batch_size = 20
        pipeline.enrichment_batch_size = 16

        class Embedder:
            def __init__(self):
                self.batch_size = 20

        class Enricher:
            def __init__(self):
                self.batch_size = 16

        pipeline.embedding_generator = Embedder()
        pipeline.contextual_enricher = Enricher()
        return pipeline

    def test_compute_batch_size_scales_down_under_pressure(self):
        pipeline = self._make_pipeline_like()
        batch = pipeline._compute_memory_aware_batch_size(
            current_batch=20,
            min_batch=4,
            max_batch=24,
            pressure_ratio=2.0,
        )
        self.assertEqual(batch, 10)

    def test_compute_batch_size_honors_minimum(self):
        pipeline = self._make_pipeline_like()
        batch = pipeline._compute_memory_aware_batch_size(
            current_batch=20,
            min_batch=4,
            max_batch=24,
            pressure_ratio=10.0,
        )
        self.assertEqual(batch, 4)

    def test_apply_controls_adjusts_batches(self):
        pipeline = self._make_pipeline_like()
        pipeline._get_available_memory_mb = lambda: 4096.0

        # Estimated memory 2048MB vs target 1024MB => pressure ratio 2x
        pipeline._apply_memory_aware_batch_controls([], estimated_chunk_memory_mb=2048.0)

        self.assertEqual(pipeline.embedding_generator.batch_size, 10)
        self.assertEqual(pipeline.contextual_enricher.batch_size, 8)
        self.assertEqual(pipeline.embedding_batch_size, 10)
        self.assertEqual(pipeline.enrichment_batch_size, 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
