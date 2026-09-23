"""Ollama adapter for Response Generation Agent (qwen3:4b-instruct / qwen3:1.7b)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .config import ResponseConfig, load_response_config
from .prompt import RESPONSE_SYSTEM_PROMPT, build_user_response_prompt


class ResponseModelUnavailableError(RuntimeError):
    """Raised when Ollama model cannot be reached or fails."""


@dataclass(frozen=True)
class ModelResponseCompletion:
    content: str
    model: str


class ResponseOllamaClient:
    """HTTP client for local Ollama chat completions."""

    def __init__(self, config: Optional[ResponseConfig] = None) -> None:
        self.config = config or load_response_config()

    def ping(self) -> None:
        url = f"{self.config.ollama_url}/api/tags"
        try:
            response = httpx.get(url, timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResponseModelUnavailableError(
                f"Cannot reach Ollama at {self.config.ollama_url}. "
                "Start it with `ollama serve`."
            ) from exc

        names = {str(item.get("name")) for item in response.json().get("models", []) if item.get("name")}
        model = self.config.ollama_model
        if names and not any(m in name for name in names for m in (model, self.config.fallback_model)):
            raise ResponseModelUnavailableError(
                f"Ollama is running but model '{model}' is not pulled. Run `ollama pull {model}`."
            )

    def generate_response_json(self, compact_context: dict[str, Any]) -> ModelResponseCompletion:
        self.ping()
        body = {
            "model": self.config.ollama_model,
            "messages": [
                {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                {"role": "user", "content": build_user_response_prompt(compact_context)},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 1024,
            },
        }
        try:
            content = self._chat(body)
            return ModelResponseCompletion(content=content, model=self.config.ollama_model)
        except ResponseModelUnavailableError:
            # Try fallback model
            body["model"] = self.config.fallback_model
            content = self._chat(body)
            return ModelResponseCompletion(content=content, model=self.config.fallback_model)

    def _chat(self, body: dict[str, Any]) -> str:
        url = f"{self.config.ollama_url}/api/chat"
        try:
            response = httpx.post(url, json=body, timeout=self.config.timeout_seconds)
        except httpx.HTTPError as exc:
            raise ResponseModelUnavailableError(f"Ollama HTTP error: {exc}") from exc

        if response.status_code >= 400:
            raise ResponseModelUnavailableError(f"Ollama HTTP {response.status_code}")

        data = response.json()
        message = data.get("message") or {}
        content = message.get("content") or data.get("response") or ""
        if not str(content).strip():
            raise ResponseModelUnavailableError("Ollama returned an empty response.")
        return str(content)
