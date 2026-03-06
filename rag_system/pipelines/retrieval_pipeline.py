import pymupdf
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image
import concurrent.futures
import time
import json
import lancedb
import logging
import math
import numpy as np
from threading import Lock
from collections import defaultdict

from rag_system.utils.ollama_client import OllamaClient
from rag_system.retrieval.retrievers import MultiVectorRetriever, GraphRetriever
from rag_system.indexing.multimodal import LocalVisionModel
from rag_system.indexing.representations import select_embedder
from rag_system.indexing.embedders import LanceDBManager
from rag_system.rerankers.reranker import QwenReranker
from rag_system.rerankers.sentence_pruner import SentencePruner
# from rag_system.indexing.chunk_store import ChunkStore

import os
from PIL import Image

# ---------------------------------------------------------------------------
# Thread-safety helpers
# ---------------------------------------------------------------------------

# 1. ColBERT (via `rerankers` lib) is not thread-safe.  We protect the actual
#    `.rank()` call with `_rerank_lock`.
_rerank_lock: Lock = Lock()

# 2. Loading a large cross-encoder or ColBERT model can easily take >1 GB of
#    RAM.  When multiple sub-queries are processed in parallel they may try to
#    instantiate the reranker simultaneously, which results in PyTorch meta
#    tensor errors.  We therefore guard the *initialisation* with its own
#    lock so only one thread carries out the heavy `from_pretrained()` call.
_ai_reranker_init_lock: Lock = Lock()

# Lock to serialise first-time Provence model load
_sentence_pruner_lock: Lock = Lock()

class RetrievalPipeline:
    """
    Orchestrates the state-of-the-art multimodal RAG pipeline.
    """
    def __init__(self, config: Dict[str, Any], ollama_client: OllamaClient, ollama_config: Dict[str, Any]):
        self.config = config
        self.ollama_config = ollama_config
        self.ollama_client = ollama_client
        
        # Support both legacy "retrievers" key and newer "retrieval" key
        self.retriever_configs = dict(self.config.get("retrievers") or self.config.get("retrieval", {}))
        if "latechunk" not in self.retriever_configs and "late_chunking" in self.retriever_configs:
            self.retriever_configs["latechunk"] = self.retriever_configs["late_chunking"]
        self.latechunk_cfg = self.retriever_configs.get("latechunk", {})
        self.storage_config = self.config["storage"]
        
        # Defer initialization to just-in-time methods
        self.db_manager = None
        self.text_embedder = None
        self.dense_retriever = None
        self.bm25_retriever = None
        # Use a private attribute to avoid clashing with the public property
        self._graph_retriever = None
        self.reranker = None
        self.ai_reranker = None
        self._chunk_window_cache: Dict[tuple, List[Dict[str, Any]]] = {}

    def _get_text_table_name(self) -> str:
        return self.storage_config.get("text_table_name") or self.config["storage"].get("text_table_name")

    def _parse_metadata_payload(self, raw_metadata: Any) -> Dict[str, Any]:
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

    def _normalize_chunk_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(record)
        metadata = self._parse_metadata_payload(normalized.get("metadata"))
        normalized["metadata"] = metadata
        normalized["document_id"] = normalized.get("document_id") or metadata.get("document_id")
        normalized["chunk_index"] = normalized.get("chunk_index") if normalized.get("chunk_index") is not None else metadata.get("chunk_index", -1)
        normalized["chunk_id"] = normalized.get("chunk_id") or metadata.get("chunk_id")
        normalized["text"] = metadata.get("original_text") or normalized.get("text") or ""
        return normalized

    def _get_document_chunk_span_lancedb(self, document_id: str, start_index: int, end_index: int, table_name: str | None = None) -> List[Dict[str, Any]]:
        db_manager = self._get_db_manager()
        if not db_manager or not document_id:
            return []

        active_table = table_name or self._get_text_table_name()
        if not active_table:
            return []

        start_index = max(0, int(start_index))
        end_index = max(start_index, int(end_index))
        cache_key = (active_table, document_id, start_index, end_index)
        cached = self._chunk_window_cache.get(cache_key)
        if cached is not None:
            return [dict(chunk) for chunk in cached]

        try:
            tbl = db_manager.get_table(active_table)
        except Exception:
            return []

        sql_filter = (
            f"document_id = {json.dumps(document_id)} "
            f"AND chunk_index >= {start_index} AND chunk_index <= {end_index}"
        )

        try:
            results = tbl.search().where(sql_filter).to_list()
            normalized = [self._normalize_chunk_record(result) for result in results]
            normalized.sort(key=lambda chunk: chunk.get("chunk_index", 0))
            self._chunk_window_cache[cache_key] = normalized
            return [dict(chunk) for chunk in normalized]
        except Exception:
            return []

    def _expand_context_chunks(self, chunks: List[Dict[str, Any]], window_size: int) -> List[Dict[str, Any]]:
        if not chunks:
            return []

        expanded_chunks: Dict[str, Dict[str, Any]] = {}
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for chunk in chunks:
            document_id = chunk.get("document_id")
            chunk_index = chunk.get("chunk_index")
            if document_id is None or chunk_index is None or chunk_index == -1:
                chunk_id = chunk.get("chunk_id") or f"fallback:{len(expanded_chunks)}"
                expanded_chunks[chunk_id] = chunk
                continue
            grouped[str(document_id)].append(chunk)

        for document_id, doc_chunks in grouped.items():
            indices = [int(chunk.get("chunk_index", -1)) for chunk in doc_chunks if chunk.get("chunk_index") is not None]
            if not indices:
                continue

            span_start = max(0, min(indices) - window_size)
            span_end = max(indices) + window_size
            span_chunks = self._get_document_chunk_span_lancedb(document_id, span_start, span_end)
            chunks_by_index = {chunk.get("chunk_index"): chunk for chunk in span_chunks}

            for seed_chunk in doc_chunks:
                center_index = seed_chunk.get("chunk_index")
                if center_index is None:
                    continue
                for idx in range(max(0, int(center_index) - window_size), int(center_index) + window_size + 1):
                    surrounding_chunk = chunks_by_index.get(idx)
                    if not surrounding_chunk:
                        continue
                    cid = surrounding_chunk.get("chunk_id") or f"{document_id}:{idx}"
                    if cid not in expanded_chunks:
                        chunk_copy = dict(surrounding_chunk)
                        if cid == seed_chunk.get("chunk_id") and "rerank_score" in seed_chunk:
                            chunk_copy["rerank_score"] = seed_chunk["rerank_score"]
                        expanded_chunks[cid] = chunk_copy

        final_docs = list(expanded_chunks.values())
        if any('rerank_score' in d for d in final_docs):
            final_docs.sort(key=lambda c: c.get('rerank_score', -1), reverse=True)
        elif any('_distance' in d for d in final_docs):
            final_docs.sort(key=lambda c: c.get('_distance', 1e9))
        elif any('score' in d for d in final_docs):
            final_docs.sort(key=lambda c: c.get('score', 0), reverse=True)
        else:
            final_docs.sort(key=lambda c: (c.get('document_id', ''), c.get('chunk_index', 0)))
        return final_docs

    def _get_db_manager(self):
        if self.db_manager is None:
            # Accept either "db_path" (preferred) or legacy "lancedb_uri"
            db_path = self.storage_config.get("db_path") or self.storage_config.get("lancedb_uri")
            if not db_path:
                raise ValueError("Storage config must contain 'db_path' or 'lancedb_uri'.")
            self.db_manager = LanceDBManager(db_path=db_path)
        return self.db_manager

    def _get_text_embedder(self):
        if self.text_embedder is None:
            from rag_system.indexing.representations import select_embedder
            self.text_embedder = select_embedder(
                self.config.get("embedding_model_name", "BAAI/bge-small-en-v1.5"),
                self.ollama_config.get("host") if isinstance(self.ollama_config, dict) else None,
            )
        return self.text_embedder

    def _get_dense_retriever(self):
        """Ensure a dense MultiVectorRetriever is always available unless explicitly disabled."""
        if self.dense_retriever is None:
            # If the config explicitly sets dense.enabled to False, respect it
            if self.retriever_configs.get("dense", {}).get("enabled", True) is False:
                return None

            try:
                db_manager = self._get_db_manager()
                text_embedder = self._get_text_embedder()
                fusion_cfg = self.config.get("fusion", {})
                self.dense_retriever = MultiVectorRetriever(
                    db_manager,
                    text_embedder,
                    vision_model=None,
                    fusion_config=fusion_cfg,
                )
            except Exception as e:
                print(f" Failed to initialise dense retriever: {e}")
                self.dense_retriever = None
        return self.dense_retriever

    def _get_bm25_retriever(self):
        if self.bm25_retriever is None and self.retriever_configs.get("bm25", {}).get("enabled"):
            try:
                print(f" Lazily initializing BM25 retriever...")
                self.bm25_retriever = BM25Retriever(
                    index_path=self.storage_config["bm25_path"],
                    index_name=self.retriever_configs["bm25"]["index_name"]
                )
                print(" BM25 retriever initialized successfully")
            except Exception as e:
                print(f" Failed to initialize BM25 retriever on demand: {e}")
                # Keep it None so we don't try again
        return self.bm25_retriever

    def _get_graph_retriever(self):
        if self._graph_retriever is None and self.retriever_configs.get("graph", {}).get("enabled"):
            self._graph_retriever = GraphRetriever(graph_path=self.storage_config["graph_path"])
        return self._graph_retriever

    def _get_reranker(self):
        """Initializes the reranker for hybrid search score fusion."""
        reranker_config = self.config.get("reranker", {})
        # This is for the LanceDB internal reranker, not the AI one.
        if self.reranker is None and reranker_config.get("type") == "linear_combination":
            rerank_weight = reranker_config.get("weight", 0.5) 
            self.reranker = lancedb.rerankers.LinearCombinationReranker(weight=rerank_weight)
            print(f" Initialized LinearCombinationReranker with weight {rerank_weight}")
        return self.reranker

    def _get_ai_reranker(self):
        """Initializes a dedicated AI-based reranker."""
        reranker_config = self.config.get("reranker", {})
        if self.ai_reranker is None and reranker_config.get("enabled"):
            # Serialise first-time initialisation so only one thread attempts
            # to load the (very large) model.  Other threads will wait and use
            # the instance once ready, preventing the meta-tensor crash.
            with _ai_reranker_init_lock:
                # Another thread may have completed init while we waited
                if self.ai_reranker is None:
                    try:
                        model_name = reranker_config.get("model_name")
                        strategy = reranker_config.get("strategy", "qwen")

                        if strategy == "rerankers-lib":
                            print(f" Initialising Answer.AI ColBERT reranker ({model_name}) via rerankers lib")
                            from rerankers import Reranker
                            self.ai_reranker = Reranker(model_name, model_type="colbert")
                        else:
                            print(f" Lazily initializing Qwen reranker ({model_name})")
                            self.ai_reranker = QwenReranker(model_name=model_name)

                        print(" AI reranker initialized successfully.")
                    except Exception as e:
                        # Leave as None so the pipeline can proceed without reranking
                        print(f" Failed to initialize AI reranker: {e}")
        return self.ai_reranker

    def _get_sentence_pruner(self):
        if getattr(self, "_sentence_pruner", None) is None:
            with _sentence_pruner_lock:
                if getattr(self, "_sentence_pruner", None) is None:
                    self._sentence_pruner = SentencePruner()
        return self._sentence_pruner

    def _get_surrounding_chunks_lancedb(self, chunk: Dict[str, Any], window_size: int) -> List[Dict[str, Any]]:
        """
        Retrieves a window of chunks around a central chunk using LanceDB.
        """
        document_id = chunk.get("document_id")
        chunk_index = chunk.get("chunk_index")

        # If essential identifiers are missing, return the chunk itself
        if document_id is None or chunk_index is None or chunk_index == -1:
            return [chunk]
        start_index = max(0, chunk_index - window_size)
        end_index = chunk_index + window_size
        results = self._get_document_chunk_span_lancedb(str(document_id), start_index, end_index)
        return results or [chunk]

    def _synthesize_final_answer(self, query: str, facts: str, *, event_callback=None) -> str:
        """Uses a text LLM to synthesize a final answer from extracted facts."""
        prompt = f"""
You are an AI assistant specialised in answering questions from retrieved context.

Context you receive
 VERIFIED FACTS  text snippets retrieved from the user's documents. Some may be irrelevant noise.  
 ORIGINAL QUESTION  the user's actual query.

Instructions
1. Evaluate each snippet for relevance to the ORIGINAL QUESTION; ignore those that do not help answer it.  
2. Synthesise an answer **using only information from the relevant snippets**.  
3. If snippets contradict one another, mention the contradiction explicitly.  
4. If the snippets do not contain the needed information, reply exactly with:  
   "I could not find that information in the provided documents."  
5. Provide a thorough, well-structured answer. Use paragraphs or bullet points where helpful, and include any relevant numbers/names exactly as they appear. There is **no strict sentence limit**, but aim for clarity over brevity.  
6. Do **not** introduce external knowledge unless step 4 applies; in that case you may add a clearly-labelled "General knowledge" sentence after the required statement.

Output format
Answer:
<your answer here>

  Retrieved Snippets  
{facts}


ORIGINAL QUESTION: "{query}"
"""
        # Stream the answer token-by-token so the caller can forward them as SSE
        answer_parts: list[str] = []
        for tok in self.ollama_client.stream_completion(
            model=self.ollama_config["generation_model"],
            prompt=prompt,
        ):
            answer_parts.append(tok)
            if event_callback:
                event_callback("token", {"text": tok})

        return "".join(answer_parts)

    def run(self, query: str, table_name: str = None, window_size_override: Optional[int] = None, event_callback=None) -> Dict[str, Any]:
        self._chunk_window_cache = {}
        try:
            start_time = time.time()
            retrieval_k = self.config.get("retrieval_k", 10)

            logger = logging.getLogger(__name__)
            logger.debug("--- Running Hybrid Search for query '%s' (table=%s) ---", query, table_name or self.storage_config.get("text_table_name"))
            
            # If a custom table_name is provided, propagate it to storage config so helper methods use it
            if table_name:
                self.storage_config["text_table_name"] = table_name

            if event_callback:
                event_callback("retrieval_started", {})
            # Unified retrieval using the refactored MultiVectorRetriever
            dense_retriever = self._get_dense_retriever()
            # Get the LanceDB reranker for initial score fusion
            lancedb_reranker = self._get_reranker()
            search_type = self.retriever_configs.get("search_type", "hybrid")
            dense_weight = float(self.retriever_configs.get("dense", {}).get("weight", self.config.get("fusion", {}).get("vec_weight", 0.5)))
            dense_weight = min(max(dense_weight, 0.0), 1.0)
            
            retrieved_docs = []
            if dense_retriever:
                dense_retriever.fusion_config["search_type"] = search_type
                dense_retriever.fusion_config["vec_weight"] = dense_weight
                dense_retriever.fusion_config["bm25_weight"] = 1.0 - dense_weight
                retrieved_docs = dense_retriever.retrieve(
                    text_query=query,
                    table_name=table_name or self.storage_config["text_table_name"],
                    k=retrieval_k,
                    reranker=lancedb_reranker,
                    search_type=search_type,
                )

            # ---------------------------------------------------------------
            # Late-Chunk retrieval (optional)
            # ---------------------------------------------------------------
            if self.latechunk_cfg.get("enabled"):
                lc_table = self.latechunk_cfg.get("lancedb_table_name") or self.latechunk_cfg.get("table_name")
                if lc_table and dense_retriever:
                    try:
                        lc_docs = dense_retriever.retrieve(
                            text_query=query,
                            table_name=lc_table,
                            k=retrieval_k,
                            reranker=lancedb_reranker,
                            search_type=search_type,
                        )
                        retrieved_docs.extend(lc_docs)
                    except Exception as e:
                        print(f"  Late-chunk retrieval failed: {e}")

            if event_callback:
                event_callback("retrieval_done", {"count": len(retrieved_docs)})
            
            retrieval_time = time.time() - start_time
            logger.debug("Retrieved %s chunks in %.2fs", len(retrieved_docs), retrieval_time)

            # -----------------------------------------------------------
            #  LATE-CHUNK MERGING (merge 1 sub-vector into central hit)
            # -----------------------------------------------------------
            if self.latechunk_cfg.get("enabled") and retrieved_docs:
                merged_count = 0
                for doc in retrieved_docs:
                    try:
                        meta = doc.get("metadata", {})
                        if meta.get("latechunk_merged"):
                            continue  # already processed
                        doc_id = doc.get("document_id")
                        cidx = doc.get("chunk_index")
                        if doc_id is None or cidx is None or cidx == -1:
                            continue
                        siblings = self._get_surrounding_chunks_lancedb(doc, window_size=1)
                        siblings = [s for s in siblings if s.get("document_id") == doc_id]
                        siblings.sort(key=lambda s: s.get("chunk_index", 0))
                        merged_text = " \n".join(s.get("text", "") for s in siblings)
                        if merged_text:
                            doc["text"] = merged_text
                            meta["latechunk_merged"] = True
                            merged_count += 1
                    except Exception as e:
                        print(f"  Late-chunk merge failed for chunk {doc.get('chunk_id')}: {e}")
                if merged_count:
                    print(f" Late-chunk merging applied to {merged_count} retrieved chunks.")

            # --- AI Reranking Step ---
            ai_reranker = self._get_ai_reranker()
            if ai_reranker and retrieved_docs:
                if event_callback:
                    event_callback("rerank_started", {"count": len(retrieved_docs)})
                print(f"\n--- Reranking top {len(retrieved_docs)} docs with AI model... ---")
                start_rerank_time = time.time()

                rerank_cfg = self.config.get("reranker", {})
                top_k_cfg = rerank_cfg.get("top_k")
                top_percent = rerank_cfg.get("top_percent")  # value in range 01

                if top_percent is not None:
                    try:
                        pct = float(top_percent)
                        assert 0 < pct <= 1
                        top_k = max(1, int(len(retrieved_docs) * pct))
                    except Exception:
                        print("  Invalid top_percent value; falling back to top_k")
                        top_k = top_k_cfg or len(retrieved_docs)
                else:
                    top_k = top_k_cfg or len(retrieved_docs)

                strategy = self.config.get("reranker", {}).get("strategy", "qwen")

                if strategy == "rerankers-lib":
                    texts = [d['text'] for d in retrieved_docs]
                    # ColBERT's Rust backend isn't Sync; serialise calls.
                    with _rerank_lock:
                        ranked = ai_reranker.rank(query=query, docs=texts)
                    # ranked is RankedResults; convert to list of (score, idx)
                    try:
                        pairs = [(r.score, r.document.doc_id) for r in ranked.results]
                        if any(p[1] is None for p in pairs):
                            pairs = [(r.score, i) for i, r in enumerate(ranked.results)]
                    except Exception:
                        pairs = ranked
                    # Keep only top_k results if requested
                    if top_k is not None and len(pairs) > top_k:
                        pairs = pairs[:top_k]
                    reranked_docs = [retrieved_docs[idx] | {"rerank_score": score} for score, idx in pairs]
                else:
                    try:
                        reranked_docs = ai_reranker.rerank(query, retrieved_docs, top_k=top_k)
                    except TypeError:
                        texts = [d['text'] for d in retrieved_docs]
                        pairs = ai_reranker.rank(query, texts, top_k=top_k)
                        reranked_docs = [retrieved_docs[idx] | {"rerank_score": score} for score, idx in pairs]

                rerank_time = time.time() - start_rerank_time
                print(f" Reranking completed in {rerank_time:.2f}s. Refined to {len(reranked_docs)} docs.")
                if event_callback:
                    event_callback("rerank_done", {"count": len(reranked_docs)})
            else:
                # If no AI reranker, proceed with the initially retrieved docs
                reranked_docs = retrieved_docs

            window_size = self.config.get("context_window_size", 1)
            if window_size_override is not None:
                window_size = window_size_override
            if window_size > 0 and reranked_docs:
                if event_callback:
                    event_callback("context_expand_started", {"count": len(reranked_docs)})
                print(f"\n--- Expanding context for {len(reranked_docs)} top documents (window size: {window_size})... ---")
                final_docs = self._expand_context_chunks(reranked_docs, window_size)
                print(f"Expanded to {len(final_docs)} unique chunks for synthesis.")
                if event_callback:
                    event_callback("context_expand_done", {"count": len(final_docs)})
            else:
                final_docs = reranked_docs

            # Optionally hide non-reranked chunks: if any chunk carries a
            # `rerank_score`, we assume the caller wants to focus on those.
            if any('rerank_score' in d for d in final_docs):
                final_docs = [d for d in final_docs if 'rerank_score' in d]

            # ------------------------------------------------------------------
            # Sentence-level pruning (Provence)
            # ------------------------------------------------------------------
            prov_cfg = self.config.get("provence", {})
            if prov_cfg.get("enabled"):
                if event_callback:
                    event_callback("prune_started", {"count": len(final_docs)})
                thresh = float(prov_cfg.get("threshold", 0.1))
                print(f"\n--- Provence pruning enabled (threshold={thresh}) ---")
                pruner = self._get_sentence_pruner()
                final_docs = pruner.prune_documents(query, final_docs, threshold=thresh)
                # Remove any chunks that were fully pruned (empty text)
                final_docs = [d for d in final_docs if d.get('text', '').strip()]
                if event_callback:
                    event_callback("prune_done", {"count": len(final_docs)})

            print("\n--- Final Documents for Synthesis ---")
            if not final_docs:
                print("No documents to synthesize.")
            else:
                for i, doc in enumerate(final_docs):
                    print(f"  [{i+1}] Chunk ID: {doc.get('chunk_id')}")
                    print(f"      Score: {doc.get('score', 'N/A')}")
                    if 'rerank_score' in doc:
                        print(f"      Rerank Score: {doc.get('rerank_score'):.4f}")
                    print(f"      Text: \"{doc.get('text', '').strip()}\"")
            print("------------------------------------")

            if not final_docs:
                return {"answer": "I could not find an answer in the documents.", "source_documents": []}
            
            # --- Sanitize docs for JSON serialization (no NaN/Inf types) ---
            def _clean_val(v):
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return None
                if isinstance(v, (np.floating,)):
                    try:
                        f = float(v)
                        if math.isnan(f) or math.isinf(f):
                            return None
                        return f
                    except Exception:
                        return None
                return v

            for doc in final_docs:
                # Remove heavy or internal-only fields before serialising
                doc.pop("vector", None)
                doc.pop("_distance", None)
                doc.pop("_fused_score", None)
                # Clean numeric fields
                for key in ['score', '_distance', 'rerank_score']:
                    if key in doc:
                        doc[key] = _clean_val(doc[key])

            context = "\n\n".join([doc['text'] for doc in final_docs])

            #  DEBUG: Show the exact context passed to the LLM after pruning
            print("\n=== Context passed to LLM (post-pruning) ===")
            if len(context) > 2000:
                print(context[:2000] + "\n[truncated] (total {} chars)".format(len(context)))
            else:
                print(context)
            print("=== End of context ===\n")

            final_answer = self._synthesize_final_answer(query, context, event_callback=event_callback)
            
            return {"answer": final_answer, "source_documents": final_docs}
        finally:
            self._chunk_window_cache.clear()

    def diagnose_retrieval(
        self,
        query: str,
        table_name: str = None,
        *,
        retrieval_k: Optional[int] = None,
        pre_rerank_k: int = 10,
        post_rerank_k: int = 10,
        search_type: Optional[str] = None,
        dense_weight: Optional[float] = None,
        apply_ai_rerank: Optional[bool] = None,
    ) -> Dict[str, Any]:
        def _clean_score(value):
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return None
            if isinstance(value, (np.floating,)):
                try:
                    cast = float(value)
                    if math.isnan(cast) or math.isinf(cast):
                        return None
                    return cast
                except Exception:
                    return None
            return value

        def _diag_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
            metadata = doc.get("metadata")
            if isinstance(metadata, str):
                metadata = self._parse_metadata_payload(metadata)
            elif not isinstance(metadata, dict):
                metadata = {}

            text = str(doc.get("text") or "")
            if len(text) > 400:
                text = text[:400] + "..."

            return {
                "chunk_id": doc.get("chunk_id"),
                "document_id": doc.get("document_id") or metadata.get("document_id"),
                "chunk_index": doc.get("chunk_index"),
                "score": _clean_score(doc.get("score")),
                "bm25": _clean_score(doc.get("bm25")),
                "distance": _clean_score(doc.get("_distance")),
                "rerank_score": _clean_score(doc.get("rerank_score")),
                "title": metadata.get("title") or metadata.get("document_title"),
                "text": text,
            }

        active_table = table_name or self.storage_config.get("text_table_name")
        if not active_table:
            raise ValueError("No table_name available for diagnostics.")

        retrieval_k = max(1, int(retrieval_k or self.config.get("retrieval_k", 10)))
        pre_rerank_k = max(1, int(pre_rerank_k))
        post_rerank_k = max(1, int(post_rerank_k))

        dense_retriever = self._get_dense_retriever()
        if dense_retriever is None:
            return {
                "query": query,
                "table_name": active_table,
                "retrieval": {
                    "search_type": search_type or self.retriever_configs.get("search_type", "hybrid"),
                    "dense_weight": dense_weight,
                    "retrieval_k": retrieval_k,
                    "pre_rerank": [],
                    "post_rerank": [],
                    "ai_rerank_applied": False,
                    "retrieved_count": 0,
                },
            }

        selected_search_type = (search_type or self.retriever_configs.get("search_type") or "hybrid").lower()
        selected_dense_weight = dense_weight
        if selected_dense_weight is None:
            selected_dense_weight = float(
                self.retriever_configs.get("dense", {}).get(
                    "weight", self.config.get("fusion", {}).get("vec_weight", 0.5)
                )
            )
        selected_dense_weight = min(max(float(selected_dense_weight), 0.0), 1.0)

        dense_retriever.fusion_config["search_type"] = selected_search_type
        dense_retriever.fusion_config["vec_weight"] = selected_dense_weight
        dense_retriever.fusion_config["bm25_weight"] = 1.0 - selected_dense_weight

        retrieved_docs = dense_retriever.retrieve(
            text_query=query,
            table_name=active_table,
            k=retrieval_k,
            reranker=self._get_reranker(),
            search_type=selected_search_type,
        )

        pre_docs = [_diag_doc(doc) for doc in retrieved_docs[:pre_rerank_k]]

        ai_rerank_enabled = self.config.get("reranker", {}).get("enabled", False)
        if apply_ai_rerank is not None:
            ai_rerank_enabled = bool(apply_ai_rerank)

        reranked_docs = list(retrieved_docs)
        ai_rerank_applied = False
        if ai_rerank_enabled and retrieved_docs:
            ai_reranker = self._get_ai_reranker()
            if ai_reranker:
                ai_rerank_applied = True
                top_k = min(max(post_rerank_k, 1), len(retrieved_docs))
                strategy = self.config.get("reranker", {}).get("strategy", "qwen")
                if strategy == "rerankers-lib":
                    texts = [doc["text"] for doc in retrieved_docs]
                    with _rerank_lock:
                        ranked = ai_reranker.rank(query=query, docs=texts)
                    try:
                        pairs = [(r.score, r.document.doc_id) for r in ranked.results]
                        if any(pair[1] is None for pair in pairs):
                            pairs = [(r.score, i) for i, r in enumerate(ranked.results)]
                    except Exception:
                        pairs = ranked
                    pairs = pairs[:top_k]
                    reranked_docs = [retrieved_docs[idx] | {"rerank_score": score} for score, idx in pairs]
                else:
                    if hasattr(ai_reranker, "rerank"):
                        reranked_docs = ai_reranker.rerank(query, retrieved_docs, top_k=top_k)
                    else:
                        texts = [doc["text"] for doc in retrieved_docs]
                        pairs = ai_reranker.rank(query, texts, top_k=top_k)
                        reranked_docs = [retrieved_docs[idx] | {"rerank_score": score} for score, idx in pairs]

        post_docs = [_diag_doc(doc) for doc in reranked_docs[:post_rerank_k]]

        return {
            "query": query,
            "table_name": active_table,
            "retrieval": {
                "search_type": selected_search_type,
                "dense_weight": selected_dense_weight,
                "retrieval_k": retrieval_k,
                "pre_rerank": pre_docs,
                "post_rerank": post_docs,
                "ai_rerank_applied": ai_rerank_applied,
                "retrieved_count": len(retrieved_docs),
                "post_rerank_count": len(reranked_docs),
            },
        }

    # ------------------------------------------------------------------
    # Public utility
    # ------------------------------------------------------------------
    def list_document_titles(self, max_items: int = 25) -> List[str]:
        """Return up to *max_items* distinct document titles (or IDs).

        This is used only for prompt-routing, so we favour robustness over
        perfect recall. If anything goes wrong we return an empty list so
        the caller can degrade gracefully.
        """
        try:
            tbl_name = self.storage_config.get("text_table_name")
            if not tbl_name:
                return []

            tbl = self._get_db_manager().get_table(tbl_name)

            field_name = "document_title" if "document_title" in tbl.schema.names else "document_id"

            # Use a cheap SQL filter to grab distinct values; fall back to a
            # simple scan if the driver lacks DISTINCT support.
            try:
                sql = f"SELECT DISTINCT {field_name} FROM tbl LIMIT {max_items}"
                rows = tbl.search().where("true").sql(sql).to_list()  # type: ignore
                titles = [r[field_name] for r in rows if r.get(field_name)]
            except Exception:
                # Fallback: scan first N rows
                rows = tbl.search().select(field_name).limit(max_items * 4).to_list()
                seen = set()
                titles = []
                for r in rows:
                    val = r.get(field_name)
                    if val and val not in seen:
                        titles.append(val)
                        seen.add(val)
                        if len(titles) >= max_items:
                            break

            # Ensure we don't exceed max_items
            return titles[:max_items]
        except Exception:
            # Any issues (missing table, bad schema, etc.) > just return []
            return []

    # -------------------- Public helper properties --------------------
    @property
    def retriever(self):
        """Lazily exposes the main (dense) retriever so external components
        like the ReAct agent tools can call `.retrieve()` directly without
        reaching into private helpers. If the retriever has not yet been
        instantiated, it is created on first access via `_get_dense_retriever`."""
        return self._get_dense_retriever()

    def update_embedding_model(self, model_name: str):
        """Switch embedding model at runtime and clear cached objects so they re-initialize."""
        if self.config.get("embedding_model_name") == model_name:
            return  # nothing to do
        print(f" RetrievalPipeline switching embedding model to '{model_name}' (was '{self.config.get('embedding_model_name')}')")
        self.config["embedding_model_name"] = model_name
        # Reset caches so new instances are built on demand
        self.text_embedder = None
        self.dense_retriever = None