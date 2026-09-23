"""Configuration for Response Generation Agent."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResponseConfig:
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct"
    fallback_model: str = "qwen3:1.7b"
    timeout_seconds: float = 30.0


def load_response_config() -> ResponseConfig:
    return ResponseConfig(
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("RESPONSE_MODEL", os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")),
        fallback_model=os.getenv("RESPONSE_FALLBACK_MODEL", "qwen3:1.7b"),
        timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT", "30.0")),
    )
