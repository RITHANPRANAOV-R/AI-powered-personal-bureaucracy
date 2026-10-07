from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.orchestration.workflow_planning.schema import WorkflowPlan
from agents.knowledge_based.information_retrieval.schemas.address_resolution import (
    AddressResolutionResult, AddressResolutionStatus,
)


class FactStatus(str, Enum):
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    SUBMITTED_PENDING = "submitted_pending"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"
    HUMAN_INTERVENTION_REQUIRED = "human_intervention_required"


class StepExecutionStatus(str, Enum):
    COMPLETED = "completed"
    SUBMITTED_PENDING = "submitted_pending"
    BLOCKED = "blocked"
    FAILED = "failed"
    HUMAN_INTERVENTION_REQUIRED = "human_intervention_required"


class AdapterStatus(str, Enum):
    COMPLETED = "completed"
    SUBMITTED_PENDING = "submitted_pending"
    FAILED = "failed"
    HUMAN_INTERVENTION_REQUIRED = "human_intervention_required"


class ConfirmedFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: Any
    provenance: str = Field(min_length=1)
    status: FactStatus
    allowed_for_execution: bool = False


class ConfirmedExecutionContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    facts: dict[str, ConfirmedFact] = Field(default_factory=dict)
    document_refs: list[str] = Field(default_factory=list)
    session_id: str = Field(min_length=1)
    application_id: Optional[str] = None

    @model_validator(mode="after")
    def preserve_address_resolution_metadata(self):
        fact = self.facts.get("address_resolution")
        if fact is None:
            return self
        resolution = AddressResolutionResult.model_validate(fact.value).model_copy(deep=True)
        if resolution.status == AddressResolutionStatus.RESOLVED:
            pin_fact = self.facts.get("pincode")
            if pin_fact is not None and str(pin_fact.value) != resolution.queried_pin:
                raise ValueError("Resolved postal PIN does not match the existing execution-context PIN.")
            new_address_fact = self.facts.get("new_address")
            resolved_context_address = resolution.context.get("new_address")
            if isinstance(resolved_context_address, dict):
                resolved_context_address = resolved_context_address.get("value")
            if new_address_fact is not None and isinstance(resolved_context_address, str):
                normalized_current = re.sub(r"\s+", " ", str(new_address_fact.value)).strip().casefold()
                normalized_resolved = re.sub(r"\s+", " ", resolved_context_address).strip().casefold()
                if normalized_current != normalized_resolved:
                    raise ValueError("Resolved postal context does not match the current confirmed new address.")
        # An attached result must not become a trusted scalar/authorized action,
        # including when the context is reconstructed from client JSON.
        self.facts["address_resolution"] = fact.model_copy(update={
            "value": resolution,
            "status": _resolution_fact_status(resolution),
            "allowed_for_execution": False,
        })
        return self

    @property
    def address_resolution(self) -> AddressResolutionResult | None:
        """One canonical object, accessible from the existing facts handoff."""
        fact = self.facts.get("address_resolution")
        return AddressResolutionResult.model_validate(fact.value) if fact is not None else None


def _resolution_fact_status(resolution: AddressResolutionResult) -> FactStatus:
    if resolution.status == AddressResolutionStatus.AMBIGUOUS:
        return FactStatus.AMBIGUOUS
    if resolution.status == AddressResolutionStatus.CONFLICT:
        return FactStatus.CONFLICTING
    # Postal resolution is evidence, not citizen authorization or VTC confirmation.
    return FactStatus.UNCONFIRMED


class ExecutionAuthorization(BaseModel):
    model_config = ConfigDict(extra="ignore")

    authorization_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=1)
    approved_step_ids: list[str] = Field(default_factory=list)
    satisfied_approval_step_ids: list[str] = Field(default_factory=list)
    approved_at: datetime
    expires_at: datetime
    revoked: bool = False


class ComplianceDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowed: bool
    policy_version: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    authorized_step_ids: list[str] = Field(default_factory=list)


class HumanIntervention(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: str = Field(min_length=1)
    required_user_action: str = Field(min_length=1)
    checkpoint_reference: str = Field(min_length=1)
    resumable: bool = True


class ResumeCheckpoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    checkpoint_reference: str = Field(min_length=1)
    completed_step_ids: list[str] = Field(default_factory=list)
    human_action_completed: bool = False


class ExecutionOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    dry_run: bool = False


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workflow_plan: WorkflowPlan
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=1)
    execution_authorization: Optional[ExecutionAuthorization] = None
    compliance_decision: ComplianceDecision
    confirmed_context: ConfirmedExecutionContext
    resume_checkpoint: Optional[ResumeCheckpoint] = None
    execution_options: ExecutionOptions = Field(default_factory=ExecutionOptions)


class AdapterResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: AdapterStatus
    outcome: str = Field(min_length=1)
    error_category: Optional[str] = None
    retryable: bool = False
    portal_reference: Optional[str] = None
    human_intervention: Optional[HumanIntervention] = None


class StepExecutionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(min_length=1)
    status: StepExecutionStatus
    action_attempted: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    error_category: Optional[str] = None
    retryable: bool = False
    portal_reference: Optional[str] = None
    human_intervention: Optional[HumanIntervention] = None
    started_at: datetime
    completed_at: datetime


class ExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_type: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    step_id: Optional[str] = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    execution_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=1)
    status: ExecutionStatus
    step_results: list[StepExecutionResult] = Field(default_factory=list)
    events: list[ExecutionEvent] = Field(default_factory=list)
    human_intervention: Optional[HumanIntervention] = None
    failure_reason: Optional[str] = None