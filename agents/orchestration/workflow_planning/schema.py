from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agents.knowledge_based.information_retrieval.schemas import RetrievalResult
from agents.orchestration.intent_understanding.schemas import IntentClassificationResult
from agents.orchestration.monitoring.schemas import SessionState


class PlanStatus(str, Enum):
    READY = "ready"
    NEEDS_USER_INPUT = "needs_user_input"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class StepType(str, Enum):
    REVIEW_EVIDENCE = "review_evidence"
    PROVIDE_INFORMATION = "provide_information"
    PREPARE_DOCUMENT = "prepare_document"
    PREPARE_INFORMATION = "prepare_information"
    HUMAN_APPROVAL = "human_approval"
    USER_ACTION = "user_action"
    EVIDENCE_GAP = "evidence_gap"


class StepStatus(str, Enum):
    NOT_STARTED = "not_started"
    READY = "ready"
    NEEDS_USER_INPUT = "needs_user_input"
    BLOCKED = "blocked"


class EvidenceSupport(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    NONE = "none"
    CONFLICTING = "conflicting"


class MissingInformationItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    field_name: Optional[str] = None
    question: str = Field(min_length=1)
    source: str = "intent"
    required: bool = True
    blocks_step_ids: list[str] = Field(default_factory=list)


class ApprovalPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    approval_id: str
    step_id: str
    reason: str
    confirmation: str


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    step_type: StepType
    status: StepStatus = StepStatus.NOT_STARTED
    depends_on: list[str] = Field(default_factory=list)
    required_fact_keys: list[str] = Field(default_factory=list)
    required_document_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_support: EvidenceSupport = EvidenceSupport.NONE
    blocking_reason: Optional[str] = None
    requires_user_action: bool = False
    requires_explicit_approval: bool = False


class WorkflowPlanningRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    planning_request_id: str = Field(default_factory=lambda: str(uuid4()))
    intent: IntentClassificationResult
    session_state: Optional[SessionState] = None
    retrieved_evidence: RetrievalResult
    user_constraints: dict[str, Any] = Field(default_factory=dict)


class WorkflowPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    planning_request_id: str
    request_id: str
    session_id: str
    domain: str = "aadhaar"
    service: str
    task: str
    target: Optional[str] = None
    plan_version: int = Field(default=1, ge=1)
    plan_status: PlanStatus
    steps: list[PlanStep] = Field(default_factory=list)
    missing_information: list[MissingInformationItem] = Field(default_factory=list)
    approval_points: list[ApprovalPoint] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())