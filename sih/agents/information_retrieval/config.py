"""Configuration for official-source retrieval. Separate models from other agents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PACKAGE_ROOT / ".env")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_EMBED_MODEL = "qwen3-embedding:0.6b"
DEFAULT_EXTRACT_MODEL = "qwen3:1.7b"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MAX_SOURCES = 6
DEFAULT_USER_AGENT = (
    "PersonalBureaucracyAssistant/1.0 "
    "(local official-source retrieval; no login; contact: local-dev)"
)
DEFAULT_CACHE_DIR = PACKAGE_ROOT / "data" / "retrieval_cache"

DEFAULT_ALLOWED_HOSTS = (
    "passportindia.gov.in",
    "www.passportindia.gov.in",
    "portal2.passportindia.gov.in",
    "mea.gov.in",
    "www.mea.gov.in",
)


@dataclass(frozen=True)
class RetrievalConfig:
    ollama_url: str
    embed_model: str
    extract_model: str
    timeout_seconds: float
    max_bytes: int
    max_sources: int
    user_agent: str
    cache_dir: Path
    allow_llm_extraction: bool


def load_retrieval_config() -> RetrievalConfig:
    timeout_raw = os.getenv("RETRIEVAL_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    max_bytes_raw = os.getenv("RETRIEVAL_MAX_BYTES", str(DEFAULT_MAX_BYTES))
    try:
        max_bytes = int(max_bytes_raw)
    except ValueError:
        max_bytes = DEFAULT_MAX_BYTES
    llm_flag = os.getenv("RETRIEVAL_USE_LLM", "true").strip().lower() in {"1", "true", "yes"}
    cache = Path(os.getenv("RETRIEVAL_CACHE_DIR", str(DEFAULT_CACHE_DIR))).expanduser()
    if not cache.is_absolute():
        cache = (PACKAGE_ROOT / cache).resolve()
    return RetrievalConfig(
        ollama_url=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        embed_model=os.getenv("RETRIEVAL_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        extract_model=os.getenv("RETRIEVAL_EXTRACT_MODEL", DEFAULT_EXTRACT_MODEL),
        timeout_seconds=timeout,
        max_bytes=max(50_000, max_bytes),
        max_sources=int(os.getenv("RETRIEVAL_MAX_SOURCES", str(DEFAULT_MAX_SOURCES))),
        user_agent=os.getenv("RETRIEVAL_USER_AGENT", DEFAULT_USER_AGENT),
        cache_dir=cache,
        allow_llm_extraction=llm_flag,
    )
