"""Optional local Ollama embeddings and grounded extraction. Sequential use only."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from .config import RetrievalConfig, load_retrieval_config
from .prompt import EVIDENCE_EXTRACTION_PROMPT, build_extraction_prompt

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class RetrievalModelUnavailable(RuntimeError):
    pass


class RetrievalOllama:
    def __init__(self, config: Optional[RetrievalConfig] = None) -> None:
        self.config = config or load_retrieval_config()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model(self.config.embed_model)
        vectors: list[list[float]] = []
        # Sequential, small batches to keep memory modest.
        for text in texts:
            payload = {"model": self.config.embed_model, "input": text[:4000]}
            url = f"{self.config.ollama_url}/api/embed"
            try:
                response = httpx.post(url, json=payload, timeout=60.0)
            except httpx.HTTPError as exc:
                raise RetrievalModelUnavailable(f"Embedding request failed: {exc}") from exc
            if response.status_code >= 400:
                # Older Ollama embeddings endpoint
                response = httpx.post(
                    f"{self.config.ollama_url}/api/embeddings",
                    json={"model": self.config.embed_model, "prompt": text[:4000]},
                    timeout=60.0,
                )
            if response.status_code >= 400:
                raise RetrievalModelUnavailable(f"Embedding HTTP {response.status_code}: {response.text[:300]}")
            data = response.json()
            embedding = None
            if isinstance(data.get("embeddings"), list) and data["embeddings"]:
                embedding = data["embeddings"][0]
            elif isinstance(data.get("embedding"), list):
                embedding = data["embedding"]
            if not embedding:
                raise RetrievalModelUnavailable("Embedding response had no vector.")
            vectors.append([float(x) for x in embedding])
        return vectors

    def extract_requirements(self, excerpts: list[dict], questions: list[str]) -> dict[str, Any]:
        self._ensure_model(self.config.extract_model)
        body = {
            "model": self.config.extract_model,
            "messages": [
                {"role": "system", "content": EVIDENCE_EXTRACTION_PROMPT},
                {"role": "user", "content": build_extraction_prompt(excerpts, questions)},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0.0, "num_predict": 700, "num_ctx": 4096},
        }
        url = f"{self.config.ollama_url}/api/chat"
        try:
            response = httpx.post(url, json=body, timeout=90.0)
        except httpx.HTTPError as exc:
            raise RetrievalModelUnavailable(f"Extraction request failed: {exc}") from exc
        if response.status_code >= 400 and body.get("think") is False:
            retry = dict(body)
            retry.pop("think", None)
            response = httpx.post(url, json=retry, timeout=90.0)
        if response.status_code >= 400:
            raise RetrievalModelUnavailable(f"Extraction HTTP {response.status_code}: {response.text[:300]}")
        content = (response.json().get("message") or {}).get("content") or ""
        return extract_json_object(str(content))

    def _ensure_model(self, model: str) -> None:
        try:
            response = httpx.get(f"{self.config.ollama_url}/api/tags", timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RetrievalModelUnavailable(
                f"Cannot reach Ollama at {self.config.ollama_url}. Start it with `ollama serve`."
            ) from exc
        names = {str(item.get("name")) for item in response.json().get("models", []) if item.get("name")}
        if names and model not in names and f"{model}:latest" not in names:
            if not any(n == model or n.startswith(f"{model}:") for n in names):
                raise RetrievalModelUnavailable(
                    f"Ollama is running but '{model}' is not pulled. Run `ollama pull {model}`."
                )


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
