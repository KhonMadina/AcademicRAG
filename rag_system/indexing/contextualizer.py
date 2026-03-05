from typing import List, Dict, Any
from rag_system.utils.ollama_client import OllamaClient
from rag_system.ingestion.chunking import create_contextual_window
import logging
import re
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the structured prompt templates, adapted from the example
SYSTEM_PROMPT = "You are an expert at summarizing and providing context for document sections based on their local surroundings."

LOCAL_CONTEXT_PROMPT_TEMPLATE = """<local_context>
{local_context_text}
</local_context>"""

CHUNK_PROMPT_TEMPLATE = """Here is the specific chunk we want to situate within the local context provided:
<chunk>
{chunk_content}
</chunk>

Based *only* on the local context provided, give a very short (2-5 sentence) context summary to situate this specific chunk. 
Focus on the chunk's topic and its relation to the immediately surrounding text shown in the local context. 
Focus on the the overall theme of the context, make sure to include topics, concepts, and other relevant information.
Answer *only* with the succinct context and nothing else."""

class ContextualEnricher:
    """
    Enriches chunks with a prepended summary of their surrounding context using Ollama,
    while preserving the original text.
    """
    def __init__(self, llm_client: OllamaClient, llm_model: str, batch_size: int = 10):
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.batch_size = batch_size
        self.max_prompt_tokens = int(os.getenv("RAG_ENRICH_PROMPT_MAX_TOKENS", "3000"))
        self.min_summary_chars = int(os.getenv("RAG_ENRICH_MIN_SUMMARY_CHARS", "5"))
        logger.info(f"Initialized ContextualEnricher with Ollama model '{self.llm_model}' (batch_size={batch_size}).")

    def _estimate_tokens(self, text: str) -> int:
        # Fast approximation to keep this independent of model tokenizers.
        return max(1, len(text) // 4)

    def _truncate_for_token_budget(self, text: str, token_budget: int) -> str:
        if token_budget <= 0:
            return ""
        # Keep head+tail for context continuity.
        approx_chars = token_budget * 4
        if len(text) <= approx_chars:
            return text
        head = int(approx_chars * 0.65)
        tail = max(0, approx_chars - head)
        return text[:head].rstrip() + "\n...\n" + text[-tail:].lstrip()

    def _build_prompt(self, local_context_text: str, chunk_text: str, budget_scale: float = 1.0) -> str:
        max_tokens = max(256, int(self.max_prompt_tokens * budget_scale))
        static_shell = (
            f"{SYSTEM_PROMPT}\n\n"
            f"{LOCAL_CONTEXT_PROMPT_TEMPLATE.format(local_context_text='')}\n\n"
            f"{CHUNK_PROMPT_TEMPLATE.format(chunk_content='')}"
        )
        static_tokens = self._estimate_tokens(static_shell)
        variable_budget = max(64, max_tokens - static_tokens)

        # Reserve more budget for current chunk than local context to guarantee relevance.
        chunk_budget = max(32, int(variable_budget * 0.6))
        context_budget = max(32, variable_budget - chunk_budget)

        bounded_chunk = self._truncate_for_token_budget(chunk_text, chunk_budget)
        bounded_context = self._truncate_for_token_budget(local_context_text, context_budget)

        human_prompt_content = (
            f"{LOCAL_CONTEXT_PROMPT_TEMPLATE.format(local_context_text=bounded_context)}\n\n"
            f"{CHUNK_PROMPT_TEMPLATE.format(chunk_content=bounded_chunk)}"
        )
        return f"{SYSTEM_PROMPT}\n\n{human_prompt_content}"

    def _fallback_summary(self, chunk_text: str) -> str:
        # Deterministic fallback: short lead sentence to avoid empty enrichment metadata.
        flat = " ".join(chunk_text.split())
        if not flat:
            return ""
        clipped = flat[:260].rstrip()
        if clipped and clipped[-1] not in ".!?":
            clipped += "..."
        return clipped

    def _generate_summary(self, local_context_text: str, chunk_text: str) -> str:
        """Generates a contextual summary using a structured, multi-part prompt."""
        for scale in (1.0, 0.75, 0.55):
            try:
                full_prompt = self._build_prompt(local_context_text, chunk_text, budget_scale=scale)
                response = self.llm_client.generate_completion(self.llm_model, full_prompt, enable_thinking=False)
                summary_raw = response.get('response', '').strip()

                # --- Sanitize the summary to remove chain-of-thought markers ---
                cleaned = re.sub(r'<think[^>]*>.*?</think>', '', summary_raw, flags=re.IGNORECASE | re.DOTALL)
                cleaned = re.sub(r'<assistant[^>]*>|</assistant>', '', cleaned, flags=re.IGNORECASE)
                if 'Answer:' in cleaned:
                    cleaned = cleaned.split('Answer:', 1)[1]

                summary = next((ln.strip() for ln in cleaned.splitlines() if ln.strip()), '')
                if not summary:
                    summary = summary_raw

                if summary and len(summary) >= self.min_summary_chars:
                    return summary

                error_text = str(response.get("error", "")).lower()
                if "prompt too long" in error_text or "max context length" in error_text:
                    logger.warning("Contextualizer prompt exceeded model context; retrying with smaller prompt budget.")
                    continue

            except Exception as e:
                logger.error(f"LLM invocation failed during contextualization (scale={scale}): {e}")

        fallback = self._fallback_summary(chunk_text)
        if fallback and len(fallback) >= self.min_summary_chars:
            logger.warning("Using fallback contextual summary due to repeated LLM truncation/failure.")
            return fallback

        logger.warning("Generated context summary is too short or empty. Skipping enrichment for this chunk.")
        return ""

    def enrich_chunks(self, chunks: List[Dict[str, Any]], window_size: int = 1) -> List[Dict[str, Any]]:
        if not chunks:
            return []

        logger.info(f"Enriching {len(chunks)} chunks with contextual summaries (window_size={window_size}) using Ollama...")
        
        # Import batch processor
        from rag_system.utils.batch_processor import BatchProcessor, estimate_memory_usage
        
        # Estimate memory usage
        memory_mb = estimate_memory_usage(chunks)
        logger.info(f"Estimated memory usage for contextual enrichment: {memory_mb:.1f}MB")
        
        # Use batch processing for better performance and progress tracking
        batch_processor = BatchProcessor(batch_size=self.batch_size)
        
        def process_chunk_batch(chunk_indices):
            """Process a batch of chunk indices for contextual enrichment"""
            batch_results = []
            for i in chunk_indices:
                chunk = chunks[i]
                try:
                    local_context_text = create_contextual_window(chunks, chunk_index=i, window_size=window_size)
                    
                    # The summary is generated based on the original, unmodified text
                    original_text = chunk['text']
                    summary = self._generate_summary(local_context_text, original_text)
                    
                    new_chunk = chunk.copy()
                    
                    # Ensure metadata is a dictionary
                    if 'metadata' not in new_chunk or not isinstance(new_chunk['metadata'], dict):
                        new_chunk['metadata'] = {}

                    # Store original text and summary in metadata
                    new_chunk['metadata']['original_text'] = original_text
                    new_chunk['metadata']['contextual_summary'] = "N/A"

                    # Prepend the context summary ONLY if it was successfully generated
                    if summary:
                        new_chunk['text'] = f"Context: {summary}\n\n---\n\n{original_text}"
                        new_chunk['metadata']['contextual_summary'] = summary
                    
                    batch_results.append(new_chunk)
                    
                except Exception as e:
                    logger.error(f"Error enriching chunk {i}: {e}")
                    # Return original chunk if enrichment fails
                    batch_results.append(chunk)
                    
            return batch_results
        
        # Create list of chunk indices for batch processing
        chunk_indices = list(range(len(chunks)))
        
        # Process chunks in batches
        enriched_chunks = batch_processor.process_in_batches(
            chunk_indices,
            process_chunk_batch,
            "Contextual Enrichment"
        )
        
        return enriched_chunks
    
    def enrich_chunks_sequential(self, chunks: List[Dict[str, Any]], window_size: int = 1) -> List[Dict[str, Any]]:
        """Sequential enrichment method (legacy) - kept for comparison"""
        if not chunks:
            return []

        logger.info(f"Enriching {len(chunks)} chunks sequentially (window_size={window_size})...")
        enriched_chunks = []
        
        for i, chunk in enumerate(chunks):
            local_context_text = create_contextual_window(chunks, chunk_index=i, window_size=window_size)
            
            # The summary is generated based on the original, unmodified text
            original_text = chunk['text']
            summary = self._generate_summary(local_context_text, original_text)
            
            new_chunk = chunk.copy()
            
            # Ensure metadata is a dictionary
            if 'metadata' not in new_chunk or not isinstance(new_chunk['metadata'], dict):
                new_chunk['metadata'] = {}

            # Store original text and summary in metadata
            new_chunk['metadata']['original_text'] = original_text
            new_chunk['metadata']['contextual_summary'] = "N/A"

            # Prepend the context summary ONLY if it was successfully generated
            if summary:
                new_chunk['text'] = f"Context: {summary}\n\n---\n\n{original_text}"
                new_chunk['metadata']['contextual_summary'] = summary
            
            enriched_chunks.append(new_chunk)
            
            if (i + 1) % 10 == 0 or i == len(chunks) - 1:
                logger.info(f"  ...processed {i+1}/{len(chunks)} chunks.")
            
        return enriched_chunks