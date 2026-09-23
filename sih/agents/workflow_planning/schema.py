"""Pydantic contracts for the Workflow Planning Agent.

IntentResult, ProfileContextResult, and RetrievedEvidenceResult are imported
and are not redefined.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agents.information_retrieval.schema import RetrievedEvidenceResult
from agents.intent_understanding.schema import IntentResult, TaskType
from agents.user_context.schema import ProfileContextResult


CONTRACT_VERSION = "1.0"
SUPPORTED_UPSTREAM_CONTRACT_VERSIONS = frozenset({CONTRACT_VERSION})


class PlanStatus(str, Enum):
    READY = "ready"
    NEEDS_USER_INPUT = "needs_user_input"
    BLOCKED = "blocked"
    PARTIAL = "partial"
    FAILED = "failed"


class StepType(str, Enum):
    VERIFY_INFORMATION = "verify_information"
    PREPARE_DOCUMENT = "prepare_document"
    REVIEW_REQUIREMENTS = "review_requirements"
    PREPARE_FORM = "prepare_form"
    MANUAL_USER_ACTION = "manual_user_action"
    HUMAN_APPROVAL = "human_approval"
    TRACK_STATUS = "track_status"
    VERIFY_COMPLETION = "verify_completion"
    OTHER = "other"


class StepStatus(str, Enum):
    NOT_STARTED = "not_started"
    READY = "ready"
    NEEDS_USER_INPUT = "needs_user_input"
    BLOCKED = "blocked"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class EvidenceSupportStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    CONFLICTING = "conflicting"
    NONE = "none"


class PlanningMode(str, Enum):
    OLLAMA = "ollama"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class RequestedModelMode(str, Enum):
    AUTO = "auto"
    OLLAMA = "ollama"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class MissingInformationItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fact_key: Optional[str] = None
    question: str
    source: str = Field(description="intent, profile, evidence, or planning")
    status: str = Field(description="unknown, unconfirmed, blocking, or clarification")
    blocks_step_ids: List[str] = Field(default_factory=list)


class UnresolvedConflict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    statement: str
    source_refs: List[str] = Field(default_factory=list)
    affected_step_ids: List[str] = Field(default_factory=list)


class EvidenceGap(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    related_step_ids: List[str] = Field(default_factory=list)
    note: str = ""


class HumanApprovalPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    approval_id: str
    step_id: str
    reason: str
    what_user_must_confirm: str


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str
    sequence: int = Field(ge=1)
    title: str
    description: str
    step_type: StepType
    status: StepStatus = StepStatus.NOT_STARTED
    depends_on: List[str] = Field(default_factory=list)
    required_fact_keys: List[str] = Field(default_factory=list)
    required_document_refs: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    evidence_status: EvidenceSupportStatus = EvidenceSupportStatus.NONE
    assumptions: List[str] = Field(default_factory=list)
    blocking_reason: Optional[str] = None
    requires_user_action: bool = False
    requires_explicit_approval: bool = False
    consequential_action: bool = False
    human_review_note: str = ""

    @field_validator("step_id")
    @classmethod
    def _step_id_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("step_id must not be empty")
        return stripped

    @field_validator("depends_on", "required_fact_keys", "required_document_refs", "evidence_ids", "assumptions")
    @classmethod
    def _dedupe_str_lists(cls, value: List[str]) -> List[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            key = str(item).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out


class WorkflowPlan(BaseModel):
    """Canonical handoff to Compliance, Execution, Monitoring, and Response agents."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    planning_request_id: str
    request_id: str = Field(description="Originating IntentResult.request_id")
    service_name: Optional[str] = None
    document_type: Optional[str] = None
    task_type: TaskType
    jurisdiction: Optional[str] = None
    language: str
    plan_id: str
    plan_version: int = Field(ge=1)
    plan_status: PlanStatus
    goal_summary: str
    steps: List[PlanStep] = Field(default_factory=list)
    missing_information: List[MissingInformationItem] = Field(default_factory=list)
    unresolved_conflicts: List[UnresolvedConflict] = Field(default_factory=list)
    evidence_gaps: List[EvidenceGap] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    human_approval_points: List[HumanApprovalPoint] = Field(default_factory=list)
    created_at: str
    planning_mode: PlanningMode


class WorkflowPlanningRequest(BaseModel):
    """Public input for `create_workflow_plan`."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    planning_request_id: str = Field(default_factory=lambda: str(uuid4()))
    intent: IntentResult
    profile_context: ProfileContextResult
    retrieved_evidence: RetrievedEvidenceResult
    current_workflow_state: Optional[WorkflowPlan] = None
    user_constraints: Dict[str, str] = Field(default_factory=dict)
    model_mode: RequestedModelMode = RequestedModelMode.AUTO

    @model_validator(mode="after")
    def _keep_typed_upstream(self) -> "WorkflowPlanningRequest":
        return self


class WorkflowPlanningValidationError(ValueError):
    """Raised when a planning request cannot be parsed as the declared contracts."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def workflow_plan_json_schema() -> dict:
    return WorkflowPlan.model_json_schema()


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts" / "workflow_plan.schema.json"


def write_workflow_plan_schema(path: Optional[Path] = None) -> Path:
    target = path or default_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(workflow_plan_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate WorkflowPlan JSON Schema from the Pydantic model.")
    parser.add_argument("--out", default=str(default_schema_path()))
    args = parser.parse_args()
    print(f"Wrote {write_workflow_plan_schema(Path(args.out))}")


if __name__ == "__main__":
    main()
