"""Replaceable local Ollama adapter for plan phrasing/order proposals only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .config import PlanningConfig, load_planning_config
from .prompt import PLANNING_SYSTEM_PROMPT, build_planning_prompt

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class PlanningModelUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PlanningCompletion:
    content: str
    model: str


class PlanningOllamaClient:
    def __init__(self, config: Optional[PlanningConfig] = None) -> None:
        self.config = config or load_planning_config()

    def propose_plan_adjustments(self, compact_input: dict[str, Any]) -> PlanningCompletion:
        user_prompt = build_planning_prompt(compact_input)
        last_error: Optional[Exception] = None
        for model in (self.config.planning_model, self.config.fallback_model):
            if not model:
                continue
            try:
                self._ensure_model(model)
                content = self._chat(model, user_prompt)
                return PlanningCompletion(content=content, model=model)
            except PlanningModelUnavailable as exc:
                last_error = exc
                continue
        raise PlanningModelUnavailable(str(last_error) if last_error else "No planning model configured.")

    def _ensure_model(self, model: str) -> None:
        url = f"{self.config.ollama_url}/api/tags"
        try:
            response = httpx.get(url, timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PlanningModelUnavailable(
                f"Cannot reach Ollama at {self.config.ollama_url}. Start it with `ollama serve`."
            ) from exc
        names = {str(item.get("name")) for item in response.json().get("models", []) if item.get("name")}
        if names and not _model_is_listed(model, names):
            available = ", ".join(sorted(names)) or "(none)"
            raise PlanningModelUnavailable(
                f"Ollama is running but '{model}' is not pulled. Run `ollama pull {model}`. Available: {available}."
            )

    def _chat(self, model: str, user_prompt: str) -> str:
        url = f"{self.config.ollama_url}/api/chat"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": PLANNING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 900,
                "num_ctx": self.config.num_ctx,
            },
        }
        try:
            response = httpx.post(url, json=body, timeout=self.config.timeout_seconds)
        except httpx.HTTPError as exc:
            raise PlanningModelUnavailable(f"Ollama request failed: {exc}") from exc
        if response.status_code >= 400 and body.get("think") is False:
            retry = dict(body)
            retry.pop("think", None)
            response = httpx.post(url, json=retry, timeout=self.config.timeout_seconds)
        if response.status_code >= 400:
            raise PlanningModelUnavailable(f"Ollama HTTP {response.status_code}: {response.text[:400]}")
        data = response.json()
        content = (data.get("message") or {}).get("content") or data.get("response") or ""
        if not str(content).strip():
            raise PlanningModelUnavailable("Ollama returned an empty completion.")
        return str(content)


def extract_json_object(raw: str) -> dict[str, Any]:
    cleaned = _THINK_RE.sub("", raw).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("Model output did not contain a JSON object.")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON was not an object.")
    return parsed


def _model_is_listed(model: str, names: set[str]) -> bool:
    if model in names or f"{model}:latest" in names:
        return True
    return any(name == model or name.startswith(f"{model}:") or model.startswith(f"{name}:") for name in names)
