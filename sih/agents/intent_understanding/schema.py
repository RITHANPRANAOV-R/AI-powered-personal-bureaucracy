"""Pydantic contracts for the Intent Understanding Agent."""

from __future__ import annotations

import argparse
import json
from enum import Enum
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "1.0"


class TaskType(str, Enum):
    REGISTER = "register"
    APPLY = "apply"
    RENEW = "renew"
    REISSUE = "reissue"
    UPDATE = "update"
    TRACK = "track"
    UNDERSTAND_REQUIREMENTS = "understand_requirements"
    OTHER = "other"
    UNKNOWN = "unknown"


class Complexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class IntentStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNABLE_TO_CLASSIFY = "unable_to_classify"


class EntitySource(str, Enum):
    USER_GOAL = "user_goal"
    USER_CONTEXT = "user_context"
    DOCUMENT_CONTEXT = "document_context"
    CONVERSATION_CONTEXT = "conversation_context"


class SourcedEntity(BaseModel):
    """A typed entity extracted from caller-supplied text only."""

    model_config = ConfigDict(extra="ignore")

    type: str = Field(description="Entity type, e.g. service, location, document, person_name")
    value: str = Field(description="Extracted entity value")
    source: EntitySource = Field(description="Which request field the entity was taken from")


class SourcedStatement(BaseModel):
    """A fact or observation with provenance."""

    model_config = ConfigDict(extra="ignore")

    text: str = Field(description="Short statement")
    source: EntitySource = Field(description="Which request field the statement was taken from")


class IntentRequest(BaseModel):
    """
    Public input contract for `understand_intent`.

    The agent does not read the filesystem, vault, browser, or a profile store.
    Optional context is only what the caller explicitly passes.
    """

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Intent contract version. Initial value is 1.0.",
    )
    request_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Caller-provided correlation ID, or a generated UUID if omitted.",
    )
    user_goal: str = Field(description="Required natural-language request from the user")
    language_preference: Optional[str] = Field(
        default=None,
        description="Optional user-stated language preference",
    )
    jurisdiction_hint: Optional[str] = Field(
        default=None,
        description="Optional location/jurisdiction explicitly supplied by the user or profile context",
    )
    user_context: str = Field(
        default="",
        description="Optional concise authorized profile/context summary supplied by the caller",
    )
    document_context: List[str] = Field(
        default_factory=list,
        description="Optional short extracted document snippets or metadata already supplied by the caller",
    )
    conversation_context: str = Field(
        default="",
        description="Optional short prior-turn context needed to interpret a follow-up",
    )

    @field_validator("user_goal")
    @classmethod
    def _goal_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("user_goal must not be empty")
        return stripped

    @field_validator("language_preference", "jurisdiction_hint")
    @classmethod
    def _blank_optional_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class IntentResult(BaseModel):
    """
    Canonical serialized output passed to later agents.

    Downstream components must consume this object, not terminal prose or raw model text.
    """

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(
        description="Intent contract version. Must match the request (1.0)."
    )
    request_id: str = Field(description="Same ID as the corresponding IntentRequest")
    original_goal: str = Field(description="User goal preserved for this run")
    normalized_goal: str = Field(
        description="Concise restatement of the user goal without added facts"
    )
    service_name: Optional[str] = Field(
        default=None,
        description="Likely government service name, or null if not identified",
    )
    document_type: Optional[str] = Field(
        default=None,
        description="Likely document or certificate type, or null if not identified",
    )
    task_type: TaskType = Field(description="Classified task type")
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Jurisdiction only when explicitly present in the request or supplied context",
    )
    entities: List[SourcedEntity] = Field(
        default_factory=list,
        description="Typed entities with provenance",
    )
    stated_facts: List[SourcedStatement] = Field(
        default_factory=list,
        description="Facts that were explicitly stated by the caller",
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Possible interpretations that remain unconfirmed",
    )
    ambiguities: List[str] = Field(
        default_factory=list,
        description="Unresolved items that block a confident classification",
    )
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="Short questions asked only when needed to identify the task or service",
    )
    language: str = Field(
        description="Stated language preference, otherwise English",
    )
    urgency: Optional[str] = Field(
        default=None,
        description="Explicit urgency if stated; otherwise null. Do not infer from unrelated wording.",
    )
    complexity: Complexity = Field(description="Estimated workflow complexity")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated confidence that the classification is correct, from 0 to 1",
    )
    status: IntentStatus = Field(description="Classification completeness for downstream routing")

    @field_validator("service_name", "document_type", "jurisdiction", "urgency")
    @classmethod
    def _blank_optional_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip()
        if not stripped or stripped.lower() in {"null", "none", "unknown", "n/a"}:
            return None
        return stripped


def intent_result_json_schema() -> dict:
    """JSON Schema derived from the Pydantic IntentResult model."""
    return IntentResult.model_json_schema()


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts" / "intent_result.schema.json"


def write_intent_result_schema(path: Optional[Path] = None) -> Path:
    """Regenerate contracts/intent_result.schema.json from the live Pydantic model."""
    target = path or default_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(intent_result_json_schema(), indent=2, ensure_ascii=False)
    target.write_text(payload + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate IntentResult JSON Schema from the Pydantic model.")
    parser.add_argument(
        "--out",
        default=str(default_schema_path()),
        help="Output path for intent_result.schema.json",
    )
    args = parser.parse_args()
    written = write_intent_result_schema(Path(args.out))
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
