from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.orchestration.workflow_planning.schema import WorkflowPlan
from agents.utility_based.execution_assistance.schema import (
    ComplianceDecision,
    ConfirmedExecutionContext,
    ExecutionAuthorization,
    ExecutionOptions,
    ExecutionResult,
    ResumeCheckpoint,
)


class IntegrationStatus(str, Enum):
    BLOCKED_BY_PLAN = "blocked_by_plan"
    BLOCKED_BY_MISSING_INFORMATION = "blocked_by_missing_information"
    BLOCKED_BY_COMPLIANCE = "blocked_by_compliance"
    BLOCKED_BY_AUTHORIZATION = "blocked_by_authorization"
    EXECUTION_BLOCKED = "execution_blocked"
    HUMAN_INTERVENTION_REQUIRED = "human_intervention_required"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_PARTIAL = "execution_partial"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_PENDING = "execution_pending"


class ApprovalState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    required_step_ids: list[str] = Field(default_factory=list)
    satisfied_step_ids: list[str] = Field(default_factory=list)
    missing_step_ids: list[str] = Field(default_factory=list)


class IntegrationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workflow_plan: Optional[WorkflowPlan] = None
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=1)
    execution_authorization: Optional[ExecutionAuthorization] = None
    confirmed_context: ConfirmedExecutionContext
    resume_checkpoint: Optional[ResumeCheckpoint] = None
    execution_options: ExecutionOptions = Field(default_factory=ExecutionOptions)


class IntegrationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: IntegrationStatus
    plan_id: Optional[str] = None
    plan_version: Optional[int] = None
    compliance_decision: Optional[ComplianceDecision] = None
    approval_state: ApprovalState = Field(default_factory=ApprovalState)
    execution_result: Optional[ExecutionResult] = None
    blocking_reason: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
