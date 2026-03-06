import lancedb
import pickle
import json
from typing import List, Dict, Any
import numpy as np
import networkx as nx
import os
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import torch
import logging
import pandas as pd
import math
import concurrent.futures
from functools import lru_cache

from rag_system.indexing.embedders import LanceDBManager
from rag_system.indexing.representations import QwenEmbedder
from rag_system.indexing.multimodal import LocalVisionModel
from rag_system.utils.logging_utils import log_retrieval_results

# BM25Retriever is no longer needed.
# class BM25Retriever: ...

from fuzzywuzzy import process


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _row_identity(record: Dict[str, Any]) -> str:
    return str(
        record.get("_rowid")
        or record.get("chunk_id")
        or f"{record.get('document_id', '')}:{record.get('chunk_index', '')}"
    )


def _parse_metadata_payload(raw_metadata: Any) -> Dict[str, Any]:
    if isinstance(raw_metadata, dict):
        parsed = raw_metadata
    elif isinstance(raw_metadata, str):
        try:
            parsed = json.loads(raw_metadata)
        except json.JSONDecodeError:
            return {}
    else:
        return {}

    if not isinstance(parsed, dict):
        return {}

    # Backward compatibility: older indexes stored the full chunk object.
    nested = parsed.get("metadata")
    if isinstance(nested, dict):
        merged = nested.copy()
        if parsed.get("text") and "original_text" not in merged:
            merged["original_text"] = parsed["text"]
        for key in ("document_id", "chunk_index", "chunk_id", "document_title", "title"):
            if key in parsed and key not in merged:
                merged[key] = parsed[key]
        return merged

    return parsed.copy()


def _score_record(record: Dict[str, Any], source: str) -> float:
    if source == "fts":
        return _safe_float(record.get("score"))
    return 1.0 / (1.0 + _safe_float(record.get("_distance"), default=1e9))


def _normalize_scores(records: List[Dict[str, Any]], source: str) -> Dict[str, float]:
    if not records:
        return {}

    raw_scores = { _row_identity(record): _score_record(record, source) for record in records }
    values = list(raw_scores.values())
    min_score = min(values)
    max_score = max(values)
    if max_score - min_score <= 1e-12:
        return {key: 1.0 for key in raw_scores}
    return {key: (score - min_score) / (max_score - min_score) for key, score in raw_scores.items()}


def _fuse_ranked_results(
    fts_records: List[Dict[str, Any]],
    vec_records: List[Dict[str, Any]],
    *,
    method: str,
    bm25_weight: float,
    vec_weight: float,
    rrf_k: int,
) -> List[Dict[str, Any]]:
    combined: Dict[str, Dict[str, Any]] = {}

    for record in fts_records + vec_records:
        combined.setdefault(_row_identity(record), record)

    if method == "rrf":
        fused_scores = {key: 0.0 for key in combined}
        for rank, record in enumerate(fts_records, start=1):
            fused_scores[_row_identity(record)] += bm25_weight / (rrf_k + rank)
        for rank, record in enumerate(vec_records, start=1):
            fused_scores[_row_identity(record)] += vec_weight / (rrf_k + rank)
    else:
        fts_norm = _normalize_scores(fts_records, "fts")
        vec_norm = _normalize_scores(vec_records, "vec")
        fused_scores = {
            key: bm25_weight * fts_norm.get(key, 0.0) + vec_weight * vec_norm.get(key, 0.0)
            for key in combined
        }

    ranked = sorted(combined.values(), key=lambda record: fused_scores.get(_row_identity(record), 0.0), reverse=True)
    for record in ranked:
        record["_fused_score"] = fused_scores.get(_row_identity(record), 0.0)
    return ranked

class GraphRetriever:
    def __init__(self, graph_path: str):
        self.graph = nx.read_gml(graph_path)

    def retrieve(self, query: str, k: int = 5, score_cutoff: int = 80) -> List[Dict[str, Any]]:
        print(f"\n--- Performing Graph Retrieval for query: '{query}' ---")
        
        query_parts = query.split()
        entities = []
        for part in query_parts:
            match = process.extractOne(part, self.graph.nodes(), score_cutoff=score_cutoff)
            if match and isinstance(match[0], str):
                entities.append(match[0])
        
        retrieved_docs = []
        for entity in set(entities):
            for neighbor in self.graph.neighbors(entity):
                retrieved_docs.append({
                    'chunk_id': f"graph_{entity}_{neighbor}",
                    'text': f"Entity: {entity}, Neighbor: {neighbor}",
                    'score': 1.0,
                    'metadata': {'source': 'graph'}
                })
        
        print(f"Retrieved {len(retrieved_docs)} documents from the graph.")
        return retrieved_docs[:k]

# region === MultiVectorRetriever ===
class MultiVectorRetriever:
    """
    Performs hybrid (vector + FTS) or vector-only retrieval.
    """
    def __init__(self, db_manager: LanceDBManager, text_embedder: QwenEmbedder, vision_model: LocalVisionModel = None, *, fusion_config: Dict[str, Any] | None = None):
        self.db_manager = db_manager
        self.text_embedder = text_embedder
        self.vision_model = vision_model
        self.fusion_config = fusion_config or {"method": "linear", "bm25_weight": 0.5, "vec_weight": 0.5}

        # Lightweight in-memory LRU cache for single-query embeddings (256 entries)
        @lru_cache(maxsize=256)
        def _embed_single(q: str):
            return self.text_embedder.create_embeddings([q])[0]

        self._embed_single = _embed_single

    def retrieve(self, text_query: str, table_name: str, k: int, reranker=None, search_type: str | None = None) -> List[Dict[str, Any]]:
        """
        Performs a search on a single LanceDB table.
        If a reranker is provided, it performs a hybrid search.
        Otherwise, it performs a standard vector search.
        """
        print(f"\n--- Performing Retrieval for query: '{text_query}' on table '{table_name}' ---")
        
        try:
            if table_name is None:
                table_name = "default_text_table"
            tbl = self.db_manager.get_table(table_name)
            
            # Create / fetch cached text embedding for the query
            text_query_embedding = self._embed_single(text_query)
            
            logger = logging.getLogger(__name__)
            search_mode = (search_type or self.fusion_config.get("search_type", "hybrid") or "hybrid").lower()
            method = str(self.fusion_config.get("method", "rrf") or "rrf").lower()
            candidate_multiplier = max(1, int(self.fusion_config.get("candidate_multiplier", 2)))
            candidate_k = max(k, k * candidate_multiplier)
            bm25_weight = _safe_float(self.fusion_config.get("bm25_weight", 0.5), default=0.5)
            vec_weight = _safe_float(self.fusion_config.get("vec_weight", 0.5), default=0.5)

            total_weight = bm25_weight + vec_weight
            if total_weight <= 0:
                bm25_weight = vec_weight = 0.5
                total_weight = 1.0
            bm25_weight /= total_weight
            vec_weight /= total_weight

            # Always perform hybrid lexical + vector search
            logger.debug(
                "Running retrieval on table '%s' (mode=%s, k=%s, have_reranker=%s)",
                table_name,
                search_mode,
                k,
                bool(reranker),
            )

            if reranker:
                logger.debug("Hybrid + reranker path not yet implemented with manual fusion; proceeding without extra reranker.")

            do_fts = search_mode in {"hybrid", "fts", "fts_only", "keyword"}
            do_vec = search_mode in {"hybrid", "vector", "vector_only", "dense"}

            # Run FTS and vector search in parallel to cut latency
            def _run_fts():
                if not do_fts:
                    return pd.DataFrame()
                # Very short queries often underperform  add fuzzy wildcard
                fts_query = text_query
                if len(text_query.split()) == 1:
                    fts_query = f"{text_query}* OR {text_query}~"
                try:
                    return (
                         tbl.search(query=fts_query, query_type="fts")
                            .limit(candidate_k)
                            .to_df()
                     )
                except Exception as e:
                    logger.warning("FTS leg failed on table '%s': %s", table_name, e)
                    return pd.DataFrame()

            def _run_vec():
                if not do_vec:
                    return pd.DataFrame()
                return (
                    tbl.search(text_query_embedding)
                       .limit(candidate_k)
                       .to_df()
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                fts_future = executor.submit(_run_fts)
                vec_future = executor.submit(_run_vec)
                fts_df = fts_future.result()
                vec_df = vec_future.result()

            fts_records = fts_df.to_dict(orient="records") if not fts_df.empty else []
            vec_records = vec_df.to_dict(orient="records") if not vec_df.empty else []

            if do_fts and not do_vec:
                ranked_records = fts_records
            elif do_vec and not do_fts:
                ranked_records = vec_records
            else:
                ranked_records = _fuse_ranked_results(
                    fts_records,
                    vec_records,
                    method=method,
                    bm25_weight=bm25_weight,
                    vec_weight=vec_weight,
                    rrf_k=max(10, int(self.fusion_config.get("rrf_k", 60))),
                )

            ranked_records = ranked_records[:k]
            logger.debug(
                "Retrieval complete (fts=%s, vec=%s)  %s final chunks",
                len(fts_records),
                len(vec_records),
                len(ranked_records),
            )
            
            retrieved_docs = []
            for row in ranked_records:
                metadata = _parse_metadata_payload(row.get('metadata'))
                # Add top-level fields back into metadata for consistency if they don't exist
                metadata.setdefault('document_id', row.get('document_id'))
                metadata.setdefault('chunk_index', row.get('chunk_index'))
                metadata.setdefault('chunk_id', row.get('chunk_id'))
                
                # Determine score (vector distance or FTS). Replace NaN with 0.0
                raw_score = row.get('_distance') if '_distance' in row else row.get('score')
                combined_score = row.get('_fused_score')
                if combined_score is None:
                    combined_score = _safe_float(raw_score)

                retrieved_docs.append({
                    'chunk_id': row.get('chunk_id'),
                    'text': metadata.get('original_text') or row.get('text') or '',
                    'score': combined_score,
                    'bm25': row.get('score'),
                    '_distance': row.get('_distance'),
                    'document_id': row.get('document_id') or metadata.get('document_id'),
                    'chunk_index': row.get('chunk_index') if row.get('chunk_index') is not None else metadata.get('chunk_index'),
                    'metadata': metadata
                })

            logger.debug("Hybrid search returned %s results", len(retrieved_docs))
            log_retrieval_results(retrieved_docs, k)
            print(f"Retrieved {len(retrieved_docs)} documents.")
            return retrieved_docs
        
        except Exception as e:
            print(f"Could not search table '{table_name}': {e}")
            return []
# endregion

if __name__ == '__main__':
    print("retrievers.py updated for LanceDB FTS Hybrid Search.")
