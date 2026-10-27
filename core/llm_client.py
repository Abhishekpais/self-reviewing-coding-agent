import time
from typing import Optional, Type, TypeVar
from pydantic import BaseModel
import requests

from core.config import COLAB_OLLAMA_URL, OLLAMA_MODEL

T = TypeVar("T", bound=BaseModel)


class OllamaColabClient:
    """REST Client for Gemma hosted on Google Colab with auto-model resolution."""

    def __init__(
        self,
        base_url: str = COLAB_OLLAMA_URL,
        model: str = OLLAMA_MODEL,
        timeout_sec: int = 180,
    ) -> None:
        if not base_url or "replace-with-your-tunnel" in base_url:
            raise ValueError("COLAB_OLLAMA_URL is not configured in .env!")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec
        self._resolved_model: Optional[str] = None

    def get_installed_models(self) -> list[str]:
        """Fetch the list of models currently installed on the Colab Ollama server."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=15)
            resp.raise_for_status()
            return [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Cannot reach Colab Ollama server at {self.base_url}/api/tags ({exc}). "
                "Check that your Google Colab notebook is running and update COLAB_OLLAMA_URL in .env if Colab restarted."
            ) from exc

    def resolve_active_model(self) -> str:
        """Ensure self.model matches an installed model on the Colab server to prevent 404 errors."""
        if self._resolved_model:
            return self._resolved_model

        installed = self.get_installed_models()
        if not installed:
            raise RuntimeError(
                f"Connected to {self.base_url}, but 0 models are installed in Ollama! "
                "Re-run Cell 1 in Google Colab to pull gemma4:12b / gemma4:e4b."
            )

        if self.model in installed:
            self._resolved_model = self.model
            return self._resolved_model

        # Check prefix match (e.g. 'gemma4:e4b' vs 'gemma4:latest') or pick first installed model
        for candidate in installed:
            if candidate.startswith(self.model.split(":")[0]):
                print(f"[OllamaColabClient] Auto-matched model '{self.model}' -> '{candidate}' on Colab.")
                self._resolved_model = candidate
                return self._resolved_model

        print(f"[OllamaColabClient] Model '{self.model}' not found in {installed}. Using '{installed[0]}' instead.")
        self._resolved_model = installed[0]
        return self._resolved_model

    def health_check(self) -> bool:
        active = self.resolve_active_model()
        print(f"[OllamaColabClient] Connected to {self.base_url} | Active Model: {active}")
        return True

    def chat_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        temperature: float = 0.1,
        max_retries: int = 3,
    ) -> T:
        """Query Ollama /api/chat with strict Pydantic JSON Schema enforcement."""
        active_model = self.resolve_active_model()
        payload = {
            "model": active_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": response_model.model_json_schema(),
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,
            },
        }

        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout_sec,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code} from {self.base_url}/api/chat: {resp.text}")
                raw_content = resp.json().get("message", {}).get("content", "")
                return response_model.model_validate_json(raw_content)
            except Exception as exc:
                last_err = exc
                if attempt < max_retries:
                    time.sleep(2 ** attempt)

        raise RuntimeError(f"Failed structured LLM call after {max_retries} attempts: {last_err}")