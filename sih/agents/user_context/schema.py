"""Pydantic contracts for the User Context & Profile Agent.

IntentResult is imported from the Intent Understanding Agent and is not redefined.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.intent_understanding.schema import IntentResult, TaskType


CONTRACT_VERSION = "1.0"
SNAKE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ProfileStatus(str, Enum):
    READY = "ready"
    NEEDS_USER_INPUT = "needs_user_input"
    CONFLICTS_FOUND = "conflicts_found"
    NO_RELEVANT_CONTEXT = "no_relevant_context"
    PARTIAL = "partial"
    FAILED = "failed"


class FactStatus(str, Enum):
    USER_CONFIRMED = "user_confirmed"
    DOCUMENT_EXTRACTED = "document_extracted"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class FactSourceType(str, Enum):
    USER = "user"
    PROFILE = "profile"
    DOCUMENT = "document"
    DERIVED = "derived"


class Sensitivity(str, Enum):
    ORDINARY = "ordinary"
    PERSONAL = "personal"
    HIGHLY_SENSITIVE = "highly_sensitive"


class ProcessingMode(str, Enum):
    DETERMINISTIC = "deterministic"
    OLLAMA = "ollama"
    MIXED = "mixed"


class FileScanStatus(str, Enum):
    READ = "read"
    UNSUPPORTED = "unsupported"
    UNREADABLE = "unreadable"
    SKIPPED = "skipped"


class ConsentAction(str, Enum):
    SAVE = "save"
    USE_ONCE = "use_once"
    SKIP = "skip"


class ProfileFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(description="Normalized stable snake_case key")
    value: str = Field(description="Extracted or proposed value; must not be a secret")
    status: FactStatus
    source_type: FactSourceType
    source_ref: str = Field(
        description="Safe relative file path or profile key; never an absolute path"
    )
    extracted_at: str = Field(description="ISO-8601 timestamp")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    relevant_to: str = Field(description="Why this fact matters for the current goal")
    sensitivity: Sensitivity = Sensitivity.ORDINARY
    confirmed_by_user: bool = False

    @field_validator("key")
    @classmethod
    def _snake_key(cls, value: str) -> str:
        key = value.strip().lower()
        if not SNAKE_KEY.match(key):
            raise ValueError("key must be snake_case")
        return key

    @field_validator("confirmed_by_user")
    @classmethod
    def _confirmed_matches_status(cls, value: bool, info) -> bool:
        return bool(value)


class FactConflict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    competing_values: List[str] = Field(default_factory=list)
    source_refs: List[str] = Field(default_factory=list)
    note: str = ""


class ScannedFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    relative_path: str
    status: FileScanStatus
    media_type: str = "unknown"
    character_count: Optional[int] = None
    warning: Optional[str] = None


class ConsentUpdate(BaseModel):
    """Records a persistence decision. Does not include secret or full identifier values."""

    model_config = ConfigDict(extra="ignore")

    key: str
    action: ConsentAction
    persisted: bool = False


class ProfileContextRequest(BaseModel):
    """Public input for `build_user_context`. Paths come from the application/CLI, not documents."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    request_id: str
    intent: IntentResult
    vault_dir: str = Field(description="Directory the user authorizes this agent to read")
    profile_path: str = Field(description="Local profile JSON path configured by the application")
    requested_fact_keys: List[str] = Field(default_factory=list)
    user_preferences: Dict[str, str] = Field(default_factory=dict)
    allow_model_extraction: bool = True
    save_confirmed_facts: bool = False

    @field_validator("requested_fact_keys")
    @classmethod
    def _normalize_keys(cls, value: List[str]) -> List[str]:
        keys: list[str] = []
        for raw in value:
            key = raw.strip().lower().replace(" ", "_")
            if key and key not in keys:
                keys.append(key)
        return keys


class ProfileContextResult(BaseModel):
    """Canonical handoff to Information Retrieval and Workflow Planning."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(description="Profile contract version. Initial value is 1.0.")
    request_id: str
    intent_request_id: str
    service_name: Optional[str] = None
    task_type: TaskType
    jurisdiction: Optional[str] = None
    profile_status: ProfileStatus
    relevant_facts: List[ProfileFact] = Field(default_factory=list)
    missing_requested_facts: List[str] = Field(default_factory=list)
    conflicts: List[FactConflict] = Field(default_factory=list)
    questions_for_user: List[str] = Field(default_factory=list)
    scanned_files: List[ScannedFile] = Field(default_factory=list)
    consent_updates: List[ConsentUpdate] = Field(default_factory=list)
    profile_updated: bool = False
    processing_mode: ProcessingMode = ProcessingMode.DETERMINISTIC
    warnings: List[str] = Field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def profile_result_json_schema() -> dict:
    return ProfileContextResult.model_json_schema()


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts" / "profile_context_result.schema.json"


def write_profile_result_schema(path: Optional[Path] = None) -> Path:
    target = path or default_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(profile_result_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ProfileContextResult JSON Schema.")
    parser.add_argument("--out", default=str(default_schema_path()))
    args = parser.parse_args()
    print(f"Wrote {write_profile_result_schema(Path(args.out))}")


if __name__ == "__main__":
    main()
