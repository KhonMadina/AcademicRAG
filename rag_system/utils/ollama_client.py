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
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            if format:
                payload["format"] = format
            
            if images:
                payload["images"] = [self._image_to_base64(img) for img in images]

            # Optional: disable thinking mode for Qwen3 / DeepSeek models
            if enable_thinking is not None and self._supports_chat_template_kwargs(model):
                payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

            response = self._request_with_resilience("POST", "generate", json=payload)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                # Compatibility fallback: some Ollama/model combinations reject chat_template_kwargs
                if (
                    response.status_code == 400
                    and "chat_template_kwargs" in payload
                ):
                    fallback_payload = payload.copy()
                    fallback_payload.pop("chat_template_kwargs", None)
                    response = self._request_with_resilience("POST", "generate", json=fallback_payload)
                    response.raise_for_status()
                else:
                    raise e

            response_lines = response.text.strip().split('\n')
            final_response = json.loads(response_lines[-1])
            return final_response

        except requests.exceptions.RequestException as e:
            resp = getattr(e, "response", None)
            detail = self._error_text(resp)
            print(f"Error generating completion: {e}; response={detail}")
            return {
                "response": "",
                "error": detail or str(e),
                "status_code": getattr(resp, "status_code", None),
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

        payload = {"model": model, "prompt": prompt, "stream": False}
        if format:
            payload["format"] = format
        if images:
            payload["images"] = [self._image_to_base64(img) for img in images]

        if enable_thinking is not None and self._supports_chat_template_kwargs(model):
            payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

        if self._is_circuit_open():
            print("Async Ollama completion blocked: circuit breaker is open")
            return {}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{self.api_url}/generate", json=payload)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if resp.status_code == 400 and "chat_template_kwargs" in payload:
                        fallback_payload = payload.copy()
                        fallback_payload.pop("chat_template_kwargs", None)
                        resp = await client.post(f"{self.api_url}/generate", json=fallback_payload)
                        resp.raise_for_status()
                    else:
                        raise e
                if 500 <= resp.status_code < 600:
                    self._record_failure()
                    raise httpx.HTTPStatusError("Transient Ollama server error", request=resp.request, response=resp)
                self._record_success()
                return json.loads(resp.text.strip().split("\n")[-1])
        except (httpx.HTTPError, asyncio.CancelledError) as e:
            self._record_failure()
            print(f"Async Ollama completion error: {e}")
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
        payload: Dict[str, Any] = {"model": model, "prompt": prompt, "stream": True}
        if images:
            payload["images"] = [self._image_to_base64(img) for img in images]
        if enable_thinking is not None and self._supports_chat_template_kwargs(model):
            payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

        with self._request_with_resilience("POST", "generate", json=payload, stream=True) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    # Keep-alive newline
                    continue
                try:
                    data = json.loads(raw_line.decode())
                except json.JSONDecodeError:
                    continue
                # The Ollama streaming API sends objects like {"response":"Hi","done":false}
                chunk = data.get("response", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break

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