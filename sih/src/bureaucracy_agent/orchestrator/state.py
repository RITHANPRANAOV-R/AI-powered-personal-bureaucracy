"""Typed state model for the Personal Bureaucracy Assistant Orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.bureaucracy_agent.orchestrator.statuses import WorkflowStatus

STATE_VERSION = "1.0"


class OrchestratorState(BaseModel):
    """End-to-end typed state container with backward-compatible loading."""

    model_config = ConfigDict(extra="ignore")

    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    state_version: str = STATE_VERSION
    current_node: str = "START"
    workflow_status: WorkflowStatus = WorkflowStatus.RUNNING
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # User request configuration
    user_goal: str = ""
    language: str = "en"
    is_demo: bool = False
    is_dry_run: bool = False
    stop_before_submit: bool = False
    vault_dir: str = "data/vault"
    profile_path: str = "data/profile.example.json"

    # Specialist agent results (JSON dict representations)
    intent_result: Optional[Dict[str, Any]] = None
    profile_result: Optional[Dict[str, Any]] = None
    evidence_result: Optional[Dict[str, Any]] = None
    workflow_plan_original: Optional[Dict[str, Any]] = None  # Original plan from agent
    workflow_plan: Optional[Dict[str, Any]] = None           # Scoped plan view for execution
    user_handled_steps: List[Dict[str, Any]] = Field(default_factory=list)
    validation_result: Optional[Dict[str, Any]] = None       # Pre-execution validation
    post_validation_result: Optional[Dict[str, Any]] = None  # Post-execution validation
    execution_result: Optional[Dict[str, Any]] = None
    monitoring_result: Optional[Dict[str, Any]] = None
    citizen_response: Optional[Dict[str, Any]] = None

    # Safety, Authorization & Consent tracking
    user_authorizations: List[Dict[str, Any]] = Field(default_factory=list)
    submission_consent: bool = False
    submission_attempted: bool = False
    confirmation_observed: bool = False
    terminal_reason: str = ""
    gate_reasons: List[str] = Field(default_factory=list)
    user_input_payload: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)

    def update_timestamp(self) -> None:
        """Refresh the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat()


def load_state_dict(data: Dict[str, Any]) -> OrchestratorState:
    """Backward-compatible deserializer for saved OrchestratorState."""
    data = dict(data)
    status_raw = str(data.get("workflow_status", "RUNNING")).upper()
    status_map = {
        "IDLE": WorkflowStatus.RUNNING,
        "IN_PROGRESS": WorkflowStatus.RUNNING,
        "NEEDS_USER_INPUT": WorkflowStatus.PAUSED_NEEDS_INPUT,
        "AUTHORIZATION_REQUIRED": WorkflowStatus.PAUSED_NEEDS_AUTHORIZATION,
    }
    if status_raw in status_map:
        data["workflow_status"] = status_map[status_raw]
    elif status_raw in WorkflowStatus.__members__:
        data["workflow_status"] = WorkflowStatus[status_raw]
    else:
        data["workflow_status"] = WorkflowStatus.RUNNING

    return OrchestratorState.model_validate(data)
