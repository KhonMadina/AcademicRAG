from collections import OrderedDict
from typing import List, Any, Dict, Tuple
import json
from rag_system.utils.ollama_client import OllamaClient

class QueryDecomposer:
    _SYSTEM_PROMPT = """
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
""".strip()

    _FEW_SHOT_EXAMPLES = """
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
""".strip()

    def __init__(self, llm_client: OllamaClient, llm_model: str):
        self.llm_client = llm_client
        self.llm_model = llm_model
        # Small in-memory LRU cache to avoid repeat decomposition for near-identical turns.
        self._cache: OrderedDict[Tuple[str, str, int], List[str]] = OrderedDict()
        self._cache_max_entries = 256

    def _make_cache_key(self, query: str, chat_history_text: str, max_sub_queries: int) -> Tuple[str, str, int]:
        return (query.strip().lower(), chat_history_text.strip().lower(), int(max_sub_queries))

    def _cache_get(self, key: Tuple[str, str, int]) -> List[str] | None:
        value = self._cache.get(key)
        if value is None:
            return None
        # Refresh recency for LRU behavior.
        self._cache.move_to_end(key)
        return list(value)

    def _cache_set(self, key: Tuple[str, str, int], value: List[str]) -> None:
        self._cache[key] = list(value)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max_entries:
            self._cache.popitem(last=False)

    def _extract_json_object(self, text: str) -> Dict[str, Any]:
        payload = str(text or "").strip()
        if payload.startswith("```json"):
            payload = payload[7:]
        if payload.startswith("```"):
            payload = payload[3:]
        if payload.endswith("```"):
            payload = payload[:-3]
        payload = payload.strip()

        # Fast path.
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
                return {}
        return {}

    def _normalize_output(self, data: Dict[str, Any], query: str, max_sub_queries: int) -> List[str]:
        resolved_query = str(data.get("resolved_query") or query).strip() or query
        requires_decomposition = bool(data.get("requires_decomposition", False))

        raw_sub_queries = data.get("sub_queries")
        if not isinstance(raw_sub_queries, list):
            raw_sub_queries = []

        normalized_sub_queries: List[str] = []
        for item in raw_sub_queries:
            text = str(item).strip()
            if text:
                normalized_sub_queries.append(text)

        if not requires_decomposition:
            normalized_sub_queries = [resolved_query]
        elif not normalized_sub_queries:
            normalized_sub_queries = [resolved_query]

        # De-duplicate while preserving order.
        normalized_sub_queries = list(dict.fromkeys(normalized_sub_queries))

        safe_limit = max(1, int(max_sub_queries or 1))
        return normalized_sub_queries[:safe_limit]

    def decompose(
        self,
        query: str,
        chat_history: List[Dict[str, Any]] | None = None,
        max_sub_queries: int = 10,
    ) -> List[str]:
        """Decompose *query* into standalone sub-queries.

        Parameters
        ----------
        query : str
            The latest user message.
        chat_history : list[dict] | None
            Recent conversation turns (each item should contain at least the original
            user query under the key "query"). Only the last 5 turns are
            included to keep the prompt short.
        """

        query = str(query or "").strip()
        if not query:
            return [""]

        # ---- Limit history to last 5 user turns and extract the queries ----
        history_snippets: List[str] = []
        if chat_history:
            # Keep only the last 5 turns
            recent_turns = chat_history[-5:]
            # Extract user queries (fallback: full dict as string if key missing)
            for turn in recent_turns:
                snippet = str(turn.get("query", turn)).strip().replace("\n", " ")
                if snippet:
                    # Bound each snippet to keep prompt compact.
                    history_snippets.append(snippet[:200])

        # Serialize chat_history for the prompt (single string)
        chat_history_text = " | ".join(history_snippets)

        cache_key = self._make_cache_key(query, chat_history_text, max_sub_queries)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        full_prompt = (
            self._SYSTEM_PROMPT
            + "\n\n"
            + self._FEW_SHOT_EXAMPLES
            + """



Now process

Input payload:

""" + json.dumps({"query": query, "chat_history": chat_history_text}, indent=2) + """
"""
        )

        # ---- Call the LLM ----
        response = self.llm_client.generate_completion(self.llm_model, full_prompt, format="json")

        response_text = response.get('response', '{}')
        data = self._extract_json_object(response_text)
        if not data:
            print(f"Failed to decode JSON from query decomposer: {response_text}")
            return [query]

        reasoning = data.get('reasoning', 'No reasoning provided.')
        print(f"Query Decomposition Reasoning: {reasoning}")

        sub_queries = self._normalize_output(data, query, max_sub_queries)
        self._cache_set(cache_key, sub_queries)
        return sub_queries

class HyDEGenerator:
    def __init__(self, llm_client: OllamaClient, llm_model: str):
        self.llm_client = llm_client
        self.llm_model = llm_model

    def generate(self, query: str) -> str:
        prompt = f"Generate a short, hypothetical document that answers the following question. The document should be dense with keywords and concepts related to the query.\n\nQuery: {query}\n\nHypothetical Document:"
        response = self.llm_client.generate_completion(self.llm_model, prompt)
        return response.get('response', '')

class GraphQueryTranslator:
    def __init__(self, llm_client: OllamaClient, llm_model: str):
        self.llm_client = llm_client
        self.llm_model = llm_model

    def _generate_translation_prompt(self, query: str) -> str:
        return f"""
You are an expert query planner. Convert the user's question into a structured JSON query for a knowledge graph.
The JSON should contain a 'start_node' (the known entity in the query) and an 'edge_label' (the relationship being asked about).
The graph has nodes (entities) and directed edges (relationships). For example, (Tim Cook) -[IS_CEO_OF]-> (Apple).
Return ONLY the JSON object.

User Question: "{query}"

JSON Output:
"""

    def translate(self, query: str) -> Dict[str, Any]:
        prompt = self._generate_translation_prompt(query)
        response = self.llm_client.generate_completion(self.llm_model, prompt, format="json")
        try:
            return json.loads(response.get('response', '{}'))
        except json.JSONDecodeError:
            return {}