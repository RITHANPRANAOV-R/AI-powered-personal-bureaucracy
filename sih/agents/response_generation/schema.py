"""Pydantic contracts for the Response Generation Agent.

Upstream contracts IntentResult, ProfileContextResult, RetrievedEvidenceResult,
WorkflowPlan, ValidationResult, ExecutionResult, and MonitoringResult are imported unchanged.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agents.compliance_validation.schema import ValidationResult
from agents.execution_assistance.schema import ExecutionResult
from agents.information_retrieval.schema import RetrievedEvidenceResult
from agents.intent_understanding.schema import IntentResult
from agents.monitoring_update.schema import MonitoringResult
from agents.user_context.schema import ProfileContextResult
from agents.workflow_planning.schema import WorkflowPlan


CONTRACT_VERSION = "1.0"


class OverallStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    ACTION_REQUIRED = "action_required"
    BLOCKED = "blocked"
    UNCERTAIN = "uncertain"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    COMPLETED = "completed"


class DetailLevel(str, Enum):
    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


class GenerationMode(str, Enum):
    OLLAMA = "ollama"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class CompletedActionRecord(BaseModel):
    """Action that has been completed and verified."""

    model_config = ConfigDict(extra="ignore")

    action_title: str
    status: str
    source_reference: str
    completed_at: str


class PendingActionRecord(BaseModel):
    """Outstanding action awaiting user or execution agent."""

    model_config = ConfigDict(extra="ignore")

    step_id: str
    action_title: str
    reason: str
    assigned_to: str


class CitizenNextStep(BaseModel):
    """One clear immediate next step for the citizen."""

    model_config = ConfigDict(extra="ignore")

    title: str
    description: str
    action_type: str = Field(description="user_action, explicit_approval, manual_portal_check, or review")
    required_user_phrase: Optional[str] = Field(default=None, description="Exact phrase required if approval step")


class MissingItemRecord(BaseModel):
    """Missing unconfirmed fact or document blocking workflow."""

    model_config = ConfigDict(extra="ignore")

    item_key: str
    description: str
    item_type: str = Field(description="fact, document, or approval")
    status: str


class ImportantDetailRecord(BaseModel):
    """Key ground detail (fee, deadline, reference ID) with evidence citation."""

    model_config = ConfigDict(extra="ignore")

    label: str
    value: str
    category: str = Field(description="fee, deadline, appointment, or reference_id")
    source_evidence_id: Optional[str] = Field(default=None)


class OfficialLinkRecord(BaseModel):
    """Allowlisted official portal link."""

    model_config = ConfigDict(extra="ignore")

    title: str
    url: str
    related_evidence_ids: List[str] = Field(default_factory=list)


class EvidenceReferenceMap(BaseModel):
    """Mapping connecting factual response statements to evidence IDs or events."""

    model_config = ConfigDict(extra="ignore")

    claim_statement: str
    evidence_ids: List[str] = Field(default_factory=list)
    source_type: str = Field(description="official_evidence, plan, validation, execution, or monitoring")


class ResponseGenerationRequest(BaseModel):
    """Public input contract for `generate_citizen_response`."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    response_request_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str = Field(description="Originating intent request_id")
    intent: IntentResult
    profile_context: ProfileContextResult
    retrieved_evidence: RetrievedEvidenceResult
    workflow_plan: WorkflowPlan
    validation_result: ValidationResult
    execution_result: Optional[ExecutionResult] = Field(default=None)
    monitoring_result: Optional[MonitoringResult] = Field(default=None)
    response_language: Optional[str] = Field(
        default=None,
        description="Explicit user-selected language; defaults to intent.language",
    )
    detail_level: DetailLevel = Field(default=DetailLevel.STANDARD)
    include_sensitive_values: bool = Field(
        default=False,
        description="Always false for initial version; sensitive IDs masked by default",
    )


class CitizenResponse(BaseModel):
    """Canonical output contract of the Response Generation Agent."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    response_request_id: str = Field(description="Response request correlation ID")
    request_id: str = Field(description="Originating Intent request_id")
    plan_id: Optional[str] = Field(default=None, description="Workflow plan ID")
    headline: str = Field(description="Short status headline")
    overall_status: OverallStatus = Field(description="Calculated overall workflow status")
    summary: str = Field(description="1-3 plain-language sentences grounded in inputs")
    completed_actions: List[CompletedActionRecord] = Field(default_factory=list)
    pending_actions: List[PendingActionRecord] = Field(default_factory=list)
    citizen_next_step: Optional[CitizenNextStep] = Field(default=None)
    missing_items: List[MissingItemRecord] = Field(default_factory=list)
    important_details: List[ImportantDetailRecord] = Field(default_factory=list)
    official_links: List[OfficialLinkRecord] = Field(default_factory=list)
    evidence_references: List[EvidenceReferenceMap] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    language: str = Field(description="Selected response language")
    formatted_markdown: str = Field(description="Complete ready-to-display markdown response")
    generated_at: str = Field(description="ISO-8601 timestamp with timezone")
    generation_mode: GenerationMode = Field(description="ollama or deterministic_fallback")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def citizen_response_json_schema() -> dict:
    return CitizenResponse.model_json_schema()


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts" / "citizen_response.schema.json"


def write_citizen_response_schema(path: Optional[Path] = None) -> Path:
    target = path or default_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(citizen_response_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CitizenResponse JSON Schema.")
    parser.add_argument("--out", default=str(default_schema_path()))
    args = parser.parse_args()
    print(f"Wrote {write_citizen_response_schema(Path(args.out))}")


if __name__ == "__main__":
    main()
