from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.knowledge_based.information_retrieval.schemas import RetrievalResult, UserDocumentInput
from agents.orchestration.integration.schema import IntegrationResult
from agents.orchestration.intent_understanding.schemas import IntentClassificationResult, UserRequestInput
from agents.orchestration.monitoring.schemas import ChangeDelta, SessionState
from agents.orchestration.workflow_planning.schema import WorkflowPlan
from agents.utility_based.execution_assistance.schema import (
    ConfirmedExecutionContext,
    ExecutionAuthorization,
    ExecutionEvent,
    ResumeCheckpoint,
)


class OrchestrationStatus(str, Enum):
    NEEDS_CLARIFICATION = "needs_clarification"
    RETRIEVAL_BLOCKED = "retrieval_blocked"
    PLANNING_FAILED = "planning_failed"
    COMPLIANCE_BLOCKED = "compliance_blocked"
    AUTHORIZATION_BLOCKED = "authorization_blocked"
    AWAITING_HUMAN_ACTION = "awaiting_human_action"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_PENDING = "execution_pending"
    EXECUTION_PARTIAL = "execution_partial"
    EXECUTION_FAILED = "execution_failed"
    COMPLETED = "completed"
    FAILED = "failed"


class OrchestrationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_request: UserRequestInput
    previous_session_state: Optional[SessionState] = None
    user_documents: list[UserDocumentInput] = Field(default_factory=list)
    user_constraints: dict[str, Any] = Field(default_factory=dict)
    execution_authorization: Optional[ExecutionAuthorization] = None
    confirmed_context: Optional[ConfirmedExecutionContext] = None
    resume_checkpoint: Optional[ResumeCheckpoint] = None


class OrchestrationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    request_id: str
    status: OrchestrationStatus
    intent_result: Optional[IntentClassificationResult] = None
    session_state: Optional[SessionState] = None
    session_changes: list[ChangeDelta] = Field(default_factory=list)
    retrieval_result: Optional[RetrievalResult] = None
    workflow_plan: Optional[WorkflowPlan] = None
    integration_result: Optional[IntegrationResult] = None
    execution_events: list[ExecutionEvent] = Field(default_factory=list)
    response_result: Any = None
    blocking_reason: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
