"""Configuration for the User Context & Profile Agent. Separate from the Intent Agent model."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PACKAGE_ROOT / ".env")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_PROFILE_MODEL = "qwen3:4b-instruct"
DEFAULT_PROFILE_FALLBACK_MODEL = "qwen3:1.7b"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_NUM_CTX = 8192
DEFAULT_VAULT_DIR = PACKAGE_ROOT / "data" / "vault"
DEFAULT_PROFILE_PATH = PACKAGE_ROOT / "data" / "profile.json"
EXAMPLE_PROFILE_PATH = PACKAGE_ROOT / "data" / "profile.example.json"


@dataclass(frozen=True)
class ProfileConfig:
    ollama_url: str
    profile_model: str
    fallback_model: str
    timeout_seconds: float
    num_ctx: int
    vault_dir: Path
    profile_path: Path


def load_profile_config() -> ProfileConfig:
    timeout_raw = os.getenv("PROFILE_TIMEOUT_SECONDS") or os.getenv("OLLAMA_TIMEOUT_SECONDS") or str(DEFAULT_TIMEOUT_SECONDS)
    ctx_raw = os.getenv("PROFILE_NUM_CTX", str(DEFAULT_NUM_CTX))
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    try:
        num_ctx = int(ctx_raw)
    except ValueError:
        num_ctx = DEFAULT_NUM_CTX
    vault = Path(os.getenv("VAULT_DIR", str(DEFAULT_VAULT_DIR))).expanduser()
    profile = Path(os.getenv("PROFILE_PATH", str(DEFAULT_PROFILE_PATH))).expanduser()
    if not vault.is_absolute():
        vault = (PACKAGE_ROOT / vault).resolve()
    else:
        vault = vault.resolve()
    if not profile.is_absolute():
        profile = (PACKAGE_ROOT / profile).resolve()
    else:
        profile = profile.resolve()
    return ProfileConfig(
        ollama_url=os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        profile_model=os.getenv("PROFILE_MODEL", DEFAULT_PROFILE_MODEL),
        fallback_model=os.getenv("PROFILE_FALLBACK_MODEL", DEFAULT_PROFILE_FALLBACK_MODEL),
        timeout_seconds=timeout,
        num_ctx=max(1024, min(num_ctx, 8192)),
        vault_dir=vault,
        profile_path=profile,
    )
