import requests
import json
from typing import List, Dict, Any
import os
import time
import threading
import base64
from io import BytesIO
from PIL import Image
import httpx, asyncio

class OllamaClient:
    """
    An enhanced client for Ollama that now handles image data for VLM models.
    """
    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host
        self.api_url = f"{host}/api"
        self.session = requests.Session()

        self.request_timeout = int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SEC", "60"))
        self.max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))
        self.retry_backoff_sec = float(os.getenv("OLLAMA_RETRY_BACKOFF_SEC", "1.5"))
        self.circuit_breaker_threshold = int(os.getenv("OLLAMA_CIRCUIT_BREAKER_THRESHOLD", "5"))
        self.circuit_breaker_reset_sec = int(os.getenv("OLLAMA_CIRCUIT_BREAKER_RESET_SEC", "30"))

        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._state_lock = threading.Lock()
        # (Connection check remains the same)

    def _is_circuit_open(self) -> bool:
        with self._state_lock:
            return time.time() < self._circuit_open_until

    def _record_success(self):
        with self._state_lock:
            self._failure_count = 0
            self._circuit_open_until = 0.0

    def _record_failure(self):
        with self._state_lock:
            self._failure_count += 1
            if self._failure_count >= self.circuit_breaker_threshold:
                self._circuit_open_until = time.time() + self.circuit_breaker_reset_sec

    def _request_with_resilience(self, method: str, endpoint: str, timeout: int | None = None, **kwargs):
        if self._is_circuit_open():
            raise RuntimeError("Ollama circuit breaker is open. Please retry shortly.")

        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        max_attempts = self.max_retries + 1
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=timeout or self.request_timeout,
                    **kwargs,
                )

                if 500 <= response.status_code < 600:
                    raise requests.exceptions.HTTPError(
                        f"Transient Ollama server error: {response.status_code}",
                        response=response,
                    )

                self._record_success()
                return response
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
                last_error = e
                self._record_failure()
                if attempt < max_attempts and not self._is_circuit_open():
                    time.sleep(self.retry_backoff_sec * attempt)
                    continue
                break
            except requests.exceptions.RequestException as e:
                last_error = e
                self._record_failure()
                break

        raise RuntimeError(f"Ollama request failed after {max_attempts} attempts: {last_error}")

    def _image_to_base64(self, image: Image.Image) -> str:
        """Converts a Pillow Image to a base64 string."""
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def _supports_chat_template_kwargs(self, model: str) -> bool:
        """Best-effort check: only some families reliably support chat_template_kwargs."""
        model_lc = (model or "").lower()
        return any(name in model_lc for name in ("qwen", "deepseek"))

    def _error_text(self, response: requests.Response | None) -> str:
        if response is None:
            return ""
        try:
            text = response.text or ""
            return text[:500]
        except Exception:
            return ""

    def _error_text_httpx(self, response: httpx.Response | None) -> str:
        if response is None:
            return ""
        try:
            text = response.text or ""
            return text[:500]
        except Exception:
            return ""

    def _is_prompt_too_long(self, status_code: int | None, detail: str) -> bool:
        if int(status_code or 0) != 400:
            return False
        normalized = str(detail or "").lower()
        return "prompt too long" in normalized or "max context length" in normalized

    def _normalize_completion_response(self, response_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize /api/chat and /api/generate outputs into a stable completion shape."""
        if "message" in response_payload and isinstance(response_payload["message"], dict):
            return {
                "response": response_payload["message"].get("content", ""),
                "done": response_payload.get("done", True),
                "model": response_payload.get("model"),
            }
        return response_payload

    def _generate_payload_variants(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build a small sequence of compatibility fallbacks for /api/generate."""
        variants = [payload]

        if "chat_template_kwargs" in payload:
            without_template_kwargs = payload.copy()
            without_template_kwargs.pop("chat_template_kwargs", None)
            variants.append(without_template_kwargs)

        if "format" in payload and payload.get("format") == "json":
            without_format = payload.copy()
            without_format.pop("format", None)
            # Avoid duplicates if format was already absent in a previous variant
            if all(candidate != without_format for candidate in variants):
                variants.append(without_format)

        return variants

    def _chat_payload_from_generate_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Translate a generate payload to chat payload for compatibility fallback."""
        chat_payload: Dict[str, Any] = {
            "model": payload.get("model"),
            "messages": [{"role": "user", "content": payload.get("prompt", "")}],
            "stream": payload.get("stream", False),
        }
        if payload.get("format"):
            chat_payload["format"] = payload["format"]
        return chat_payload

    def _is_prompt_too_long_response(self, response: requests.Response | None) -> bool:
        if response is None:
            return False
        return self._is_prompt_too_long(getattr(response, "status_code", 0), self._error_text(response))

    def _truncate_prompt_for_retry(self, prompt: str, attempt: int) -> str:
        """Shrink prompt size progressively when Ollama rejects oversized context."""
        prompt_text = str(prompt or "")
        if len(prompt_text) <= 2000:
            return prompt_text

        base_hard_cap = int(os.getenv("OLLAMA_PROMPT_CHAR_HARD_CAP", "12000"))
        adaptive_cap = max(1200, int(base_hard_cap * (0.55 ** max(0, attempt - 1))))
        if len(prompt_text) > adaptive_cap:
            return (
                prompt_text[:adaptive_cap]
                + "\n\n[Context truncated automatically due to model context window limits.]"
            )

        # More aggressive truncation on later retries.
        ratio = 0.65 if attempt == 1 else 0.5 if attempt == 2 else 0.35
        keep = max(1200, int(len(prompt_text) * ratio))
        return (
            prompt_text[:keep]
            + "\n\n[Context truncated automatically due to model context window limits.]"
        )

    def generate_embedding(self, model: str, text: str) -> List[float]:
        try:
            response = self._request_with_resilience(
                "POST",
                "embeddings",
                json={"model": model, "prompt": text}
            )
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return []

    def generate_completion(
        self,
        model: str,
        prompt: str,
        *,
        format: str = "",
        images: List[Image.Image] | None = None,
        enable_thinking: bool | None = None,
    ) -> Dict[str, Any]:
        """
        Generates a completion, now with optional support for images.

        Args:
            model: The name of the generation model (e.g., 'llava', 'qwen-vl').
            prompt: The text prompt for the model.
            format: The format for the response, e.g., "json".
            images: A list of Pillow Image objects to send to the VLM.
            enable_thinking: Optional flag to disable chain-of-thought for Qwen models.
        """
        current_prompt = str(prompt or "")
        max_prompt_retries = int(os.getenv("OLLAMA_PROMPT_RETRY_ATTEMPTS", "5"))

        for attempt in range(1, max_prompt_retries + 1):
            try:
                payload: Dict[str, Any] = {
                    "model": model,
                    "prompt": current_prompt,
                    "stream": False,
                }
                if format:
                    payload["format"] = format

                if images:
                    payload["images"] = [self._image_to_base64(img) for img in images]

                # Optional: disable thinking mode for Qwen3 / DeepSeek models
                if enable_thinking is not None and self._supports_chat_template_kwargs(model):
                    payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

                response = None
                for candidate_payload in self._generate_payload_variants(payload):
                    response = self._request_with_resilience("POST", "generate", json=candidate_payload)
                    if response.status_code != 400:
                        break

                # Some Ollama builds/models are stricter on /api/generate; fallback to /api/chat for text-only prompts.
                if response is not None and response.status_code == 400 and not images:
                    chat_payload = self._chat_payload_from_generate_payload(payload)
                    response = self._request_with_resilience("POST", "chat", json=chat_payload)

                if response is None:
                    return {
                        "response": "",
                        "error": "No response returned from Ollama",
                        "status_code": None,
                    }

                if self._is_prompt_too_long_response(response) and attempt < max_prompt_retries:
                    current_prompt = self._truncate_prompt_for_retry(current_prompt, attempt)
                    continue

                response.raise_for_status()
                final_response = response.json()
                return self._normalize_completion_response(final_response)

            except requests.exceptions.RequestException as e:
                resp = getattr(e, "response", None)
                detail = self._error_text(resp)
                if self._is_prompt_too_long(getattr(resp, "status_code", None), detail) and attempt < max_prompt_retries:
                    current_prompt = self._truncate_prompt_for_retry(current_prompt, attempt)
                    continue
                print(f"Error generating completion: {e}; response={detail}")
                return {
                    "response": "",
                    "error": detail or str(e),
                    "status_code": getattr(resp, "status_code", None),
                }
            except Exception as e:
                return {
                    "response": "",
                    "error": str(e),
                    "status_code": None,
                }

        return {
            "response": "",
            "error": "Prompt exceeded context window after retries",
            "status_code": 400,
        }

    # -------------------------------------------------------------
    # Async variant  uses httpx so the caller can await multiple
    # LLM calls concurrently (triage, verification, etc.).
    # -------------------------------------------------------------
    async def generate_completion_async(
        self,
        model: str,
        prompt: str,
        *,
        format: str = "",
        images: List[Image.Image] | None = None,
        enable_thinking: bool | None = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """Asynchronous version of generate_completion using httpx."""

        current_prompt = str(prompt or "")
        max_prompt_retries = int(os.getenv("OLLAMA_PROMPT_RETRY_ATTEMPTS", "5"))

        if self._is_circuit_open():
            print("Async Ollama completion blocked: circuit breaker is open")
            return {}

        for attempt in range(1, max_prompt_retries + 1):
            payload: Dict[str, Any] = {"model": model, "prompt": current_prompt, "stream": False}
            if format:
                payload["format"] = format
            if images:
                payload["images"] = [self._image_to_base64(img) for img in images]

            if enable_thinking is not None and self._supports_chat_template_kwargs(model):
                payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = None
                    for candidate_payload in self._generate_payload_variants(payload):
                        resp = await client.post(f"{self.api_url}/generate", json=candidate_payload)
                        if resp.status_code != 400:
                            break

                    if resp is not None and resp.status_code == 400 and not images:
                        chat_payload = self._chat_payload_from_generate_payload(payload)
                        resp = await client.post(f"{self.api_url}/chat", json=chat_payload)

                    if resp is None:
                        self._record_failure()
                        return {}

                    detail = self._error_text_httpx(resp)
                    if self._is_prompt_too_long(resp.status_code, detail) and attempt < max_prompt_retries:
                        current_prompt = self._truncate_prompt_for_retry(current_prompt, attempt)
                        continue

                    resp.raise_for_status()
                    if 500 <= resp.status_code < 600:
                        self._record_failure()
                        raise httpx.HTTPStatusError("Transient Ollama server error", request=resp.request, response=resp)
                    self._record_success()
                    data = resp.json()
                    return self._normalize_completion_response(data)
            except (httpx.HTTPError, asyncio.CancelledError) as e:
                self._record_failure()
                response = getattr(e, "response", None)
                detail = self._error_text_httpx(response)
                if self._is_prompt_too_long(getattr(response, "status_code", None), detail) and attempt < max_prompt_retries:
                    current_prompt = self._truncate_prompt_for_retry(current_prompt, attempt)
                    continue
                print(f"Async Ollama completion error: {e}; response={detail}")
                return {}

        return {}

    # -------------------------------------------------------------
    # Streaming variant  yields token chunks in real time
    # -------------------------------------------------------------
    def stream_completion(
        self,
        model: str,
        prompt: str,
        *,
        images: List[Image.Image] | None = None,
        enable_thinking: bool | None = None,
    ):
        """Generator that yields partial *response* strings as they arrive.

        Example:

            for tok in client.stream_completion("qwen2", "Hello"):
                print(tok, end="", flush=True)
        """
        current_prompt = str(prompt or "")
        max_prompt_retries = int(os.getenv("OLLAMA_PROMPT_RETRY_ATTEMPTS", "5"))

        for attempt in range(1, max_prompt_retries + 1):
            payload: Dict[str, Any] = {"model": model, "prompt": current_prompt, "stream": True}
            if images:
                payload["images"] = [self._image_to_base64(img) for img in images]
            if enable_thinking is not None and self._supports_chat_template_kwargs(model):
                payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

            resp = None
            for candidate_payload in self._generate_payload_variants(payload):
                resp = self._request_with_resilience("POST", "generate", json=candidate_payload, stream=True)
                if resp.status_code != 400:
                    break

            is_chat_stream = False
            if resp is not None and resp.status_code == 400 and not images:
                chat_payload = self._chat_payload_from_generate_payload(payload)
                resp = self._request_with_resilience("POST", "chat", json=chat_payload, stream=True)
                is_chat_stream = True

            # If prompt is too large, shrink and retry before failing the whole request.
            if self._is_prompt_too_long_response(resp) and attempt < max_prompt_retries:
                current_prompt = self._truncate_prompt_for_retry(current_prompt, attempt)
                continue

            if resp is None:
                raise RuntimeError("No response returned from Ollama streaming request")

            if resp.status_code == 400:
                raise RuntimeError(f"Ollama bad request: {self._error_text(resp)}")

            with resp:
                resp.raise_for_status()
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        # Keep-alive newline
                        continue
                    try:
                        data = json.loads(raw_line.decode())
                    except json.JSONDecodeError:
                        continue

                    # /api/generate streaming shape: {"response":"...","done":false}
                    if not is_chat_stream:
                        chunk = data.get("response", "")
                    else:
                        # /api/chat streaming shape: {"message":{"content":"..."},"done":false}
                        chunk = data.get("message", {}).get("content", "") if isinstance(data.get("message"), dict) else ""

                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
            return

        raise RuntimeError("Ollama request rejected after prompt truncation retries")

if __name__ == '__main__':
    # This test now requires a VLM model like 'llava' or 'qwen-vl' to be pulled.
    print("Ollama client updated for multimodal (VLM) support.")
    try:
        client = OllamaClient()
        # Create a dummy black image for testing
        dummy_image = Image.new('RGB', (100, 100), 'black')
        
        # Test VLM completion
        vlm_response = client.generate_completion(
            model="llava", # Make sure you have run 'ollama pull llava'
            prompt="What color is this image?",
            images=[dummy_image]
        )
        
        if vlm_response and 'response' in vlm_response:
            print("\n--- VLM Test Response ---")
            print(vlm_response['response'])
        else:
            print("\nFailed to get VLM response. Is 'llava' model pulled and running?")

    except Exception as e:
        print(f"An error occurred: {e}")