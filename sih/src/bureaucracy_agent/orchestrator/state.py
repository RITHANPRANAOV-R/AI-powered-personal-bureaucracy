"""Typed state model for the Bureaucracy Assistant Orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


STATE_VERSION = "1.0"


class OneRunAuthorization(BaseModel):
    """Upfront authorization record for executing workflow automation."""
    phrase: str
    scope: str = "PASSPORT SEVA REGISTRATION AND SUBMISSION"
    authorized: bool = False
    authorized_at: Optional[str] = None


class OrchestratorState(BaseModel):
    """End-to-end state tracking container for local multi-agent orchestration."""

    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    state_version: str = STATE_VERSION
    current_node: str = "START"
    workflow_status: str = "IDLE"  # IDLE, IN_PROGRESS, PAUSED_NEEDS_INPUT, PAUSED_CAPTCHA, FAILED, COMPLETED
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Execution configuration
    user_goal: str = ""
    language: str = "en"
    is_demo: bool = False
    is_dry_run: bool = False

    # Specialist Agent Outputs (stored as dicts or Pydantic representations)
    intent_result: Optional[Dict[str, Any]] = None
    profile_result: Optional[Dict[str, Any]] = None
    evidence_result: Optional[Dict[str, Any]] = None
    workflow_plan: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None
    monitoring_result: Optional[Dict[str, Any]] = None
    citizen_response: Optional[Dict[str, Any]] = None

    # Upfront Authorization & Safety tracking
    one_run_authorization: Optional[OneRunAuthorization] = None
    pending_user_question: Optional[Dict[str, Any]] = None
    user_input_payload: Dict[str, Any] = Field(default_factory=dict)
    
    # State flags
    submission_attempted: bool = False
    confirmation_observed: bool = False
    errors: List[str] = Field(default_factory=list)

    def update_timestamp(self) -> None:
        """Refresh the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat()
