
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
from typing import List, Dict, Any, Tuple, Optional

class QwenReranker:
    """
    Efficient reranker using a local Hugging Face transformer model.
    Optimized for batch inference and early exit.
    """
    def __init__(self, model_name: str = "BAAI/bge-reranker-base", verbose: bool = False) -> None:
        self.device = self._select_device()
        self.verbose = verbose
        print(f"[Reranker] Initializing BGE Reranker with model '{model_name}' on device '{self.device}'.")
        if self.device == "cpu":
            print("[Reranker][Warning] No GPU detected. Running on CPU may be slow.")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                model_name,
                torch_dtype=torch.float16 if self.device != "cpu" else None,
            ).to(self.device)
            self.model.eval()
            if self.verbose:
                print("BGE Reranker loaded successfully.")
        except Exception as e:
            print(f"[Reranker][Error] Failed to load model/tokenizer '{model_name}': {e}")
            print("[Reranker][Hint] Ensure the model name is valid and available on HuggingFace or locally. Reranking will be disabled for this session.")
            raise

    @staticmethod
    def _select_device() -> str:
        """Select the best available device: CUDA > MPS > CPU."""
        if torch.cuda.is_available():
            return "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _format_instruction(query: str, doc: str) -> str:
        instruction = 'Given a web search query, retrieve relevant passages that answer the query'
        return f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
        *,
        early_exit: bool = True,
        margin: float = 0.4,
        min_scored: int = 8,
        batch_size: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Rerank a list of documents based on their relevance to a query.

        Args:
            query: The search query string.
            documents: List of dicts, each with at least a 'text' field.
            top_k: Number of top documents to return.
            early_exit: If True, stop scoring early if margin is met.
            margin: Margin for early exit.
            min_scored: Minimum docs to score before early exit.
            batch_size: Batch size for model inference.

        Returns:
            List of reranked document dicts, each with an added 'rerank_score'.
        """
        if not documents:
            return []

        docs_sorted = sorted(documents, key=lambda d: d.get('score', 0.0), reverse=True)
        scored_pairs: List[Tuple[float, Dict[str, Any]]] = []
        total_docs = len(docs_sorted)

        with torch.inference_mode():
            for start in range(0, total_docs, batch_size):
                batch_docs = docs_sorted[start : start + batch_size]
                batch_pairs = [[query, d['text']] for d in batch_docs]

                inputs = self.tokenizer(
                    batch_pairs,
                    padding=True,
                    truncation=True,
                    return_tensors="pt",
                    max_length=512,
                ).to(self.device)

                logits = self.model(**inputs).logits.view(-1)
                batch_scores = logits.float().cpu().tolist()

                scored_pairs.extend(zip(batch_scores, batch_docs))

                # Early-exit check
                if early_exit and len(scored_pairs) >= min_scored:
                    scores = (score for score, _ in scored_pairs)
                    best_score = max(scores)
                    worst_score = min(score for score, _ in scored_pairs)
                    if best_score - worst_score >= margin:
                        if self.verbose:
                            print(f"Early exit: best {best_score:.4f}, worst {worst_score:.4f}, margin {margin}")
                        break

        # Sort and attach scores
        sorted_by_score = sorted(scored_pairs, key=lambda x: x[0], reverse=True)
        reranked_docs: List[Dict[str, Any]] = [
            {**doc, 'rerank_score': score} for score, doc in sorted_by_score[:top_k]
        ]
        return reranked_docs

if __name__ == '__main__':
    # This test requires an internet connection to download the models.
    try:
        reranker = QwenReranker(model_name="BAAI/bge-reranker-base", verbose=True)
        query = "What is the capital of France?"
        documents = [
            {'text': "Paris is the capital of France.", 'metadata': {'doc_id': 'a'}},
            {'text': "The Eiffel Tower is in Paris.", 'metadata': {'doc_id': 'b'}},
            {'text': "France is a country in Europe.", 'metadata': {'doc_id': 'c'}},
        ]
        reranked_documents = reranker.rerank(query, documents)
        print("\n--- Verification ---")
        print(f"Query: {query}")
        print("Reranked documents:")
        for doc in reranked_documents:
            print(f"  - Score: {doc['rerank_score']:.4f}, Text: {doc['text']}")
    except Exception as e:
        print(f"\nAn error occurred during the QwenReranker test: {e}")
        print("Please ensure you have an internet connection for model downloads.")
