import requests
import json
from typing import List, Dict, Any
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
        # (Connection check remains the same)

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
            response = requests.post(
                f"{self.api_url}/embeddings",
                json={"model": model, "prompt": text}
            )
            response.raise_for_status()
            return response.json().get("embedding", [])
        except requests.exceptions.RequestException as e:
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

            response = requests.post(f"{self.api_url}/generate", json=payload)
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
                    response = requests.post(f"{self.api_url}/generate", json=fallback_payload)
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
                return json.loads(resp.text.strip().split("\n")[-1])
        except (httpx.HTTPError, asyncio.CancelledError) as e:
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

        with requests.post(f"{self.api_url}/generate", json=payload, stream=True) as resp:
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