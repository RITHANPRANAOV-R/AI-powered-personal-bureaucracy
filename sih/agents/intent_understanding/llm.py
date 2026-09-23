"""Replaceable local Ollama adapter for short structured classification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .config import AgentConfig, load_config
from .prompt import INTENT_SYSTEM_PROMPT, build_user_prompt


class OllamaUnavailableError(RuntimeError):
    """Raised when the local Ollama runtime or model cannot be used."""


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ModelCompletion:
    content: str
    model: str


class OllamaClient:
    """Minimal HTTP client for Ollama chat completions. No cloud providers."""

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self.config = config or load_config()

    def ping(self) -> None:
        url = f"{self.config.ollama_url}/api/tags"
        try:
            response = httpx.get(url, timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                f"Cannot reach Ollama at {self.config.ollama_url}. "
                "Start it with `ollama serve` after installing Ollama."
            ) from exc

        names = {str(item.get("name")) for item in response.json().get("models", []) if item.get("name")}
        model = self.config.ollama_model
        if names and not _model_is_listed(model, names):
            available = ", ".join(sorted(names)) or "(none)"
            raise OllamaUnavailableError(
                f"Ollama is running but model '{model}' is not pulled. "
                f"Run `ollama pull {model}`. Available models: {available}."
            )

    def complete_json(self, request_payload: dict[str, Any]) -> ModelCompletion:
        self.ping()
        body = {
            "model": self.config.ollama_model,
            "messages": [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request_payload)},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 1024,
            },
        }
        content = self._chat(body)
        return ModelCompletion(content=content, model=self.config.ollama_model)

    def _chat(self, body: dict[str, Any]) -> str:
        url = f"{self.config.ollama_url}/api/chat"
        try:
            response = httpx.post(url, json=body, timeout=self.config.timeout_seconds)
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                f"Ollama request failed at {url}: {exc}"
            ) from exc

        if response.status_code >= 400:
            # Older Ollama builds may reject the think flag.
            if body.get("think") is False and response.status_code in {400, 404, 422}:
                retry_body = dict(body)
                retry_body.pop("think", None)
                response = httpx.post(url, json=retry_body, timeout=self.config.timeout_seconds)
            if response.status_code >= 400:
                raise OllamaUnavailableError(
                    f"Ollama returned HTTP {response.status_code}: {response.text[:500]}"
                )

        data = response.json()
        message = data.get("message") or {}
        content = message.get("content") or data.get("response") or ""
        if not str(content).strip():
            raise OllamaUnavailableError("Ollama returned an empty completion.")
        return str(content)


def _model_is_listed(model: str, names: set[str]) -> bool:
    if model in names or f"{model}:latest" in names:
        return True
    return any(name == model or name.startswith(f"{model}:") or model.startswith(f"{name}:") for name in names)


def extract_json_object(raw: str) -> dict[str, Any]:
    """Parse JSON from a model completion, stripping optional thinking tags."""
    cleaned = _THINK_RE.sub("", raw).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model output did not contain a JSON object.")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON was not an object.")
    return parsed
