

from collections import OrderedDict
from typing import List, Any, Dict, Optional, Union
import json
import logging
import hashlib
from rag_system.utils.ollama_client import OllamaClient


class QueryDecomposer:
    """
    Decomposes user queries for a Retrieval-Augmented Generation (RAG) system into standalone sub-queries.
    Uses an LLM for decomposition and caches results for efficiency.
    """

    _SYSTEM_PROMPT: str = (
        """
You are an expert at query decomposition for a Retrieval-Augmented Generation (RAG) system.

Return one RFC-8259 compliant JSON object and nothing else.
Schema:
{
  "requires_decomposition": <bool>,
  "reasoning": <string>,
  "resolved_query": <string>,
  "sub_queries": <string[]>
}

Rules:
1. Resolve context first using chat_history when references are unambiguous.
2. Use resolved_query (not raw query) to decide if decomposition is needed.
3. If requires_decomposition is false, return exactly one sub-query equal to resolved_query.
4. If requires_decomposition is true, return 2-10 standalone sub-queries.
5. Keep each sub-query self-contained and avoid pronouns.
6. Keep reasoning concise (max 50 words).

Decomposition is typically required for:
- Multi-part questions joined by "and", "also", comma lists, etc.
- Comparative/superlative questions across entities.
- Temporal/sequential comparisons.
- Enumerations (pros/cons/impacts/cost breakdowns).

Decomposition is typically not required for:
- A single factual information need.
- Queries that are too ambiguous and need clarification.
"""
    )

    _FEW_SHOT_EXAMPLES: str = (
        """
Example:
chat_history: ["What is the email address of the computer vision consultants?"]
query: "What is their revenue?"
{
  "requires_decomposition": false,
  "reasoning": "Pronoun is resolvable and this is a single information need.",
  "resolved_query": "What is the revenue of the computer vision consultants?",
  "sub_queries": ["What is the revenue of the computer vision consultants?"]
}

Example:
chat_history: []
query: "How did Nvidia's 2024 revenue compare with 2023?"
{
  "requires_decomposition": true,
  "reasoning": "Needs separate retrieval for each year before comparison.",
  "resolved_query": "How did Nvidia's 2024 revenue compare with 2023?",
  "sub_queries": [
  "What was Nvidia's revenue in 2024?",
  "What was Nvidia's revenue in 2023?"
  ]
}

Example:
chat_history: []
query: "List the pros, cons, and estimated implementation cost of adopting a vector database."
{
  "requires_decomposition": true,
  "reasoning": "Three distinct information needs.",
  "resolved_query": "List the pros, cons, and estimated implementation cost of adopting a vector database.",
  "sub_queries": [
  "What are the pros of adopting a vector database?",
  "What are the cons of adopting a vector database?",
  "What is the estimated implementation cost of adopting a vector database?"
  ]
}
"""
    )

    _MAX_HISTORY_TURNS: int = 5
    _MAX_HISTORY_SNIPPET_LEN: int = 200
    _CACHE_MAX_ENTRIES: int = 256

    def __init__(self, llm_client: OllamaClient, llm_model: str):
        self.llm_client: OllamaClient = llm_client
        self.llm_model: str = llm_model
        # Small in-memory LRU cache to avoid repeat decomposition for near-identical turns.
        self._cache: OrderedDict[str, List[str]] = OrderedDict()

    def _make_cache_key(self, query: str, chat_history_text: str, max_sub_queries: int) -> str:
        # Use a hash for large keys to keep memory usage low and lookup fast
        key_str = f"{query.strip().lower()}|{chat_history_text.strip().lower()}|{int(max_sub_queries)}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Optional[List[str]]:
        value = self._cache.get(key)
        if value is None:
            return None
        self._cache.move_to_end(key)
        return list(value)

    def _cache_set(self, key: str, value: List[str]) -> None:
        self._cache[key] = list(value)
        self._cache.move_to_end(key)
        while len(self._cache) > self._CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)

    @staticmethod
    def _extract_json_object(text: str) -> Dict[str, Any]:
        """
        Extracts a JSON object from a string, handling common LLM formatting quirks.
        """
        payload = str(text or "").strip()
        if payload.startswith("```json"):
            payload = payload[7:]
        if payload.startswith("```"):
            payload = payload[3:]
        if payload.endswith("```"):
            payload = payload[:-3]
        payload = payload.strip()

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            pass

        # Fallback: find first JSON object boundaries in noisy text.
        start = payload.find("{")
        end = payload.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(payload[start : end + 1])
            except json.JSONDecodeError:
                logging.warning("Failed to parse JSON from LLM output fallback.")
                return {}
        logging.warning("No JSON object found in LLM output.")
        return {}

    @staticmethod
    def _normalize_output(data: Dict[str, Any], query: str, max_sub_queries: int) -> List[str]:
        """
        Normalize and deduplicate sub-queries from the LLM output.
        """
        resolved_query = str(data.get("resolved_query") or query).strip() or query
        requires_decomposition = bool(data.get("requires_decomposition", False))

        raw_sub_queries = data.get("sub_queries")
        if not isinstance(raw_sub_queries, list):
            raw_sub_queries = []

        normalized_sub_queries: List[str] = [str(item).strip() for item in raw_sub_queries if str(item).strip()]

        if not requires_decomposition or not normalized_sub_queries:
            normalized_sub_queries = [resolved_query]

        # De-duplicate while preserving order.
        seen = set()
        deduped = []
        for sq in normalized_sub_queries:
            if sq not in seen:
                deduped.append(sq)
                seen.add(sq)

        safe_limit = max(1, int(max_sub_queries or 1))
        return deduped[:safe_limit]

    def decompose(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        max_sub_queries: int = 10,
    ) -> List[str]:
        """
        Decompose a query into standalone sub-queries using an LLM, with caching and prompt optimization.
        Optimizations:
        - Minimize prompt size (truncate history, avoid unnecessary whitespace)
        - Maximize cache hit rate (normalize input)
        - Avoid LLM call if query is simple
        - Add timing for performance monitoring
        """
        import time
        start_time = time.perf_counter()

        query = str(query or "").strip()
        if not query:
            return [""]

        # ---- Limit history to last N user turns and extract the queries ----
        history_snippets: List[str] = []
        if chat_history:
            # Only keep the last N turns, and only the 'query' field, truncated
            for turn in chat_history[-self._MAX_HISTORY_TURNS:]:
                snippet = str(turn.get("query", turn)).replace("\n", " ").strip()
                if snippet:
                    history_snippets.append(snippet[:self._MAX_HISTORY_SNIPPET_LEN])
        chat_history_text = " | ".join(history_snippets)

        # ---- Fast-path: skip LLM if query is trivially simple ----
        if not any(sep in query for sep in (" and ", ",", " also ", " or ", " vs ", " versus ", ";", "/")) and len(query.split()) < 16:
            # Heuristic: treat as single factual query
            return [query]

        cache_key = self._make_cache_key(query, chat_history_text, max_sub_queries)
        cached = self._cache_get(cache_key)
        if cached is not None:
            logging.debug("QueryDecomposer cache hit.")
            return cached

        # ---- Prompt construction ----
        # Use compact JSON for input payload to reduce LLM context size
        input_payload = json.dumps({"query": query, "chat_history": chat_history_text}, separators=(",", ":"))
        full_prompt = (
            f"{self._SYSTEM_PROMPT}\n\n{self._FEW_SHOT_EXAMPLES}\n\nNow process\n\nInput payload:\n\n"
            + input_payload
            + "\n"
        )

        # ---- Call the LLM ----
        try:
            response = self.llm_client.generate_completion(self.llm_model, full_prompt, format="json")
        except Exception as e:
            logging.error(f"LLM client error in query decomposition: {e}")
            return [query]

        response_text = response.get('response', '{}')
        data = self._extract_json_object(response_text)
        if not data:
            logging.warning(f"Failed to decode JSON from query decomposer: {response_text}")
            return [query]

        reasoning = data.get('reasoning', 'No reasoning provided.')
        logging.info(f"Query Decomposition Reasoning: {reasoning}")

        sub_queries = self._normalize_output(data, query, max_sub_queries)
        self._cache_set(cache_key, sub_queries)

        elapsed = time.perf_counter() - start_time
        logging.info(f"QueryDecomposer.decompose completed in {elapsed:.3f}s (sub-queries: {len(sub_queries)})")
        return sub_queries



class HyDEGenerator:
    """
    Generates a hypothetical document dense with keywords and concepts related to the query.
    """
    _PROMPT_TEMPLATE: str = (
        "Generate a short, hypothetical document that answers the following question. "
        "The document should be dense with keywords and concepts related to the query.\n\n"
        "Query: {query}\n\nHypothetical Document:"
    )

    def __init__(self, llm_client: OllamaClient, llm_model: str):
        self.llm_client: OllamaClient = llm_client
        self.llm_model: str = llm_model

    def generate(self, query: str) -> str:
        """
        Generate a hypothetical document dense with keywords and concepts for the query.
        """
        prompt = self._PROMPT_TEMPLATE.format(query=query)
        try:
            response = self.llm_client.generate_completion(self.llm_model, prompt)
            return response.get('response', '')
        except Exception as e:
            logging.error(f"LLM client error in HyDE generation: {e}")
            return ''


class GraphQueryTranslator:
    """
    Translates a user question into a structured JSON query for a knowledge graph.
    """
    _PROMPT_TEMPLATE: str = (
        """
You are an expert query planner. Convert the user's question into a structured JSON query for a knowledge graph.
The JSON should contain a 'start_node' (the known entity in the query) and an 'edge_label' (the relationship being asked about).
The graph has nodes (entities) and directed edges (relationships). For example, (Tim Cook) -[IS_CEO_OF]-> (Apple).
Return ONLY the JSON object.

User Question: "{query}"

JSON Output:
"""
    )

    def __init__(self, llm_client: OllamaClient, llm_model: str):
        self.llm_client: OllamaClient = llm_client
        self.llm_model: str = llm_model

    def _generate_translation_prompt(self, query: str) -> str:
        return self._PROMPT_TEMPLATE.format(query=query)

    def translate(self, query: str) -> Dict[str, Any]:
        """
        Translate a user question into a structured JSON query for a knowledge graph.
        """
        prompt = self._generate_translation_prompt(query)
        try:
            response = self.llm_client.generate_completion(self.llm_model, prompt, format="json")
            return json.loads(response.get('response', '{}'))
        except Exception as e:
            logging.error(f"LLM client error in graph query translation: {e}")
            return {}