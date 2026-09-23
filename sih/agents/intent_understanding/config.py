"""Runtime configuration for the Intent Understanding Agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PACKAGE_ROOT / ".env")


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:1.7b"
DEFAULT_TIMEOUT_SECONDS = 90.0


@dataclass(frozen=True)
class AgentConfig:
    ollama_url: str = DEFAULT_OLLAMA_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def load_config() -> AgentConfig:
    timeout_raw = os.getenv("OLLAMA_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    return AgentConfig(
        ollama_url=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        timeout_seconds=timeout,
    )
