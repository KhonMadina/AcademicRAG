import requests
import json
import os
import time
import threading
from typing import List, Dict, Optional

class OllamaClient:
    def __init__(self, base_url: Optional[str] = None):
        if base_url is None:
            base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.session = requests.Session()

        self.request_timeout = int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SEC", "60"))
        self.max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))
        self.retry_backoff_sec = float(os.getenv("OLLAMA_RETRY_BACKOFF_SEC", "1.5"))
        self.circuit_breaker_threshold = int(os.getenv("OLLAMA_CIRCUIT_BREAKER_THRESHOLD", "5"))
        self.circuit_breaker_reset_sec = int(os.getenv("OLLAMA_CIRCUIT_BREAKER_RESET_SEC", "30"))

        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._state_lock = threading.Lock()

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

    def _request_with_resilience(self, method: str, endpoint: str, timeout: Optional[int] = None, **kwargs):
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
    
    def is_ollama_running(self) -> bool:
        """Check if Ollama server is running"""
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def list_models(self) -> List[str]:
        """Get list of available models"""
        try:
            response = self._request_with_resilience("GET", "tags", timeout=15)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [model["name"] for model in models]
            return []
        except Exception as e:
            print(f"Error fetching models: {e}")
            return []
    
    def pull_model(self, model_name: str) -> bool:
        """Pull a model if not available"""
        try:
            response = self._request_with_resilience(
                "POST",
                "pull",
                json={"name": model_name},
                stream=True,
                timeout=max(self.request_timeout, 300),
            )
            
            if response.status_code == 200:
                print(f"Pulling model {model_name}...")
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "status" in data:
                            print(f"Status: {data['status']}")
                        if data.get("status") == "success":
                            return True
                return True
            return False
        except Exception as e:
            print(f"Error pulling model: {e}")
            return False
    
    def chat(self, message: str, model: str = "llama3.2", conversation_history: List[Dict] = None, enable_thinking: bool = True) -> str:
        """Send a chat message to Ollama"""
        if conversation_history is None:
            conversation_history = []
        
        # Add user message to conversation
        messages = conversation_history + [{"role": "user", "content": message}]
        
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
            }
            
            # Multiple approaches to disable thinking tokens
            if not enable_thinking:
                payload.update({
                    "think": False,  # Native Ollama parameter
                    "options": {
                        "think": False,
                        "thinking": False,
                        "temperature": 0.7,
                        "top_p": 0.9
                    }
                })
            else:
                payload["think"] = True
            
            response = self._request_with_resilience(
                "POST",
                "chat",
                json=payload,
                timeout=self.request_timeout,
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result["message"]["content"]
                
                # Additional cleanup: remove any thinking tokens that might slip through
                if not enable_thinking:
                    # Remove common thinking token patterns
                    import re
                    response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL | re.IGNORECASE)
                    response_text = re.sub(r'<thinking>.*?</thinking>', '', response_text, flags=re.DOTALL | re.IGNORECASE)
                    response_text = response_text.strip()
                
                return response_text
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Connection error: {e}"
    
    def chat_stream(self, message: str, model: str = "llama3.2", conversation_history: List[Dict] = None, enable_thinking: bool = True):
        """Stream chat response from Ollama"""
        if conversation_history is None:
            conversation_history = []
        
        messages = conversation_history + [{"role": "user", "content": message}]
        
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
            }
            
            # Multiple approaches to disable thinking tokens
            if not enable_thinking:
                payload.update({
                    "think": False,  # Native Ollama parameter
                    "options": {
                        "think": False,
                        "thinking": False,
                        "temperature": 0.7,
                        "top_p": 0.9
                    }
                })
            else:
                payload["think"] = True
            
            response = self._request_with_resilience(
                "POST",
                "chat",
                json=payload,
                stream=True,
                timeout=self.request_timeout,
            )
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                content = data["message"]["content"]
                                
                                # Filter out thinking tokens in streaming mode
                                if not enable_thinking:
                                    # Skip content that looks like thinking tokens
                                    if '<think>' in content.lower() or '<thinking>' in content.lower():
                                        continue
                                
                                yield content
                        except json.JSONDecodeError:
                            continue
            else:
                yield f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            yield f"Connection error: {e}"

def main():
    """Test the Ollama client"""
    client = OllamaClient()
    
    # Check if Ollama is running
    if not client.is_ollama_running():
        print(" Ollama is not running. Please start Ollama first.")
        print("Install: https://ollama.ai")
        print("Run: ollama serve")
        return
    
    print(" Ollama is running!")
    
    # List available models
    models = client.list_models()
    print(f"Available models: {models}")
    
    # Try to use llama3.2, pull if needed
    model_name = "llama3.2"
    if model_name not in [m.split(":")[0] for m in models]:
        print(f"Model {model_name} not found. Pulling...")
        if client.pull_model(model_name):
            print(f" Model {model_name} pulled successfully!")
        else:
            print(f" Failed to pull model {model_name}")
            return
    
    # Test chat
    print("\n Testing chat...")
    response = client.chat("Hello! Can you tell me a short joke?", model_name)
    print(f"AI: {response}")

if __name__ == "__main__":
    main()    