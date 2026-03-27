import json
from rag_system.utils.ollama_client import OllamaClient

from typing import Optional

class VerificationResult:
    def __init__(self, is_grounded: bool, reasoning: str, verdict: str, confidence_score: int) -> None:
        self.is_grounded: bool = is_grounded
        self.reasoning: str = reasoning
        self.verdict: str = verdict
        self.confidence_score: int = confidence_score

class Verifier:
    """
    Verifies if a generated answer is grounded in the provided context using Ollama.
    """
    def __init__(self, llm_client: OllamaClient, llm_model: str) -> None:
        self.llm_client: OllamaClient = llm_client
        self.llm_model: str = llm_model
        print(f"Initialized Verifier with Ollama model '{self.llm_model}'.")

    async def verify_async(self, query: str, context: str, answer: str) -> VerificationResult:
        """Async variant that calls the Ollama client asynchronously."""
        context_clamped = context[:4000] if context else ""
        prompt = f"""
You are an automated fact-checker. Determine whether the ANSWER is fully supported by the CONTEXT and output a single line of JSON.

# EXAMPLES

<QUERY>
What color is the sky?
</QUERY>
<CONTEXT>
During the day, the sky appears blue due to Rayleigh scattering.
</CONTEXT>
<ANSWER>
The sky is blue during the day.
</ANSWER>
<OUTPUT>
{{"verdict": "SUPPORTED", "is_grounded": true, "reasoning": "The context explicitly supports that the sky is blue during the day.", "confidence_score": 100}}
</OUTPUT>

<QUERY>
Where are apples and oranges grown?
</QUERY>
<CONTEXT>
Apples are grown in orchards.
</CONTEXT>
<ANSWER>
Apples are grown in orchards and oranges are grown in groves.
</ANSWER>
<OUTPUT>
{{"verdict": "NOT_SUPPORTED", "is_grounded": false, "reasoning": "The context mentions orchards, but not oranges or groves.", "confidence_score": 80}}
</OUTPUT>

<QUERY>
How long is the process?
</QUERY>
<CONTEXT>
The first step takes 3 days. The second step takes 5 days.
</CONTEXT>
<ANSWER>
The process takes 3 days.
</ANSWER>
<OUTPUT>
{{"verdict": "NEEDS_CLARIFICATION", "is_grounded": false, "reasoning": "The answer omits the 5 days required for the second step.", "confidence_score": 70}}
</OUTPUT>

# TASK

<QUERY>
{query}
</QUERY>
<CONTEXT>
{context_clamped}
</CONTEXT>
<ANSWER>
{answer}
</ANSWER>
<OUTPUT>
"""
        resp = await self.llm_client.generate_completion_async(self.llm_model, prompt, format="json")
        try:
            data = json.loads(resp.get("response", "{}"))
            return VerificationResult(
                is_grounded=data.get("is_grounded", False),
                reasoning=data.get("reasoning", "async parse error"),
                verdict=data.get("verdict", "NOT_SUPPORTED"),
                confidence_score=data.get('confidence_score', 0)
            )
        except (json.JSONDecodeError, AttributeError, TypeError):
            return VerificationResult(False, "Failed async parse", "NOT_SUPPORTED", 0)
