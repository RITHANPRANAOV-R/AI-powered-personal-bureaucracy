"""Configuration for Workflow Planning. Separate model from other agents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PACKAGE_ROOT / ".env")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_PLANNING_MODEL = "qwen3:4b-instruct"
DEFAULT_PLANNING_FALLBACK_MODEL = "qwen3:1.7b"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_NUM_CTX = 8192


@dataclass(frozen=True)
class PlanningConfig:
    ollama_url: str
    planning_model: str
    fallback_model: str
    timeout_seconds: float
    num_ctx: int


def load_planning_config() -> PlanningConfig:
    timeout_raw = (
        os.getenv("PLANNING_TIMEOUT_SECONDS")
        or os.getenv("OLLAMA_TIMEOUT_SECONDS")
        or str(DEFAULT_TIMEOUT_SECONDS)
    )
    ctx_raw = os.getenv("PLANNING_NUM_CTX", str(DEFAULT_NUM_CTX))
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    try:
        num_ctx = int(ctx_raw)
    except ValueError:
        num_ctx = DEFAULT_NUM_CTX
    return PlanningConfig(
        ollama_url=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        planning_model=os.getenv("PLANNING_MODEL", DEFAULT_PLANNING_MODEL),
        fallback_model=os.getenv("PLANNING_FALLBACK_MODEL", DEFAULT_PLANNING_FALLBACK_MODEL),
        timeout_seconds=timeout,
        num_ctx=max(1024, min(num_ctx, 8192)),
    )
