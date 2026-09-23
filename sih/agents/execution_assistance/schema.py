"""Pydantic contracts for the Execution & Assistance Agent.

Upstream contracts IntentResult, ProfileContextResult, RetrievedEvidenceResult,
WorkflowPlan, and ValidationResult are imported unchanged from their packages.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agents.compliance_validation.schema import ValidationResult
from agents.information_retrieval.schema import RetrievedEvidenceResult
from agents.intent_understanding.schema import IntentResult
from agents.user_context.schema import ProfileContextResult, ProfileFact
from agents.workflow_planning.schema import WorkflowPlan


CONTRACT_VERSION = "1.0"
DEFAULT_STARTING_URL = "https://www.passportindia.gov.in/psp/"
DEFAULT_ALLOWED_HOSTS = [
    "passportindia.gov.in",
    "www.passportindia.gov.in",
    "services2.passportindia.gov.in",
]


class ExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    NEEDS_USER_INPUT = "needs_user_input"
    PAUSED_FOR_USER = "paused_for_user"
    PREPARED_FOR_REVIEW = "prepared_for_review"
    SUBMISSION_ATTEMPTED = "submission_attempted"
    CONFIRMATION_OBSERVED = "confirmation_observed"
    UNCERTAIN = "uncertain"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


class StepExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    NEEDS_USER_INPUT = "needs_user_input"
    PAUSED_FOR_USER = "paused_for_user"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class UserExecutionApproval(BaseModel):
    """Step-scoped explicit user execution approval record."""

    model_config = ConfigDict(extra="ignore")

    approval_id: str = Field(default_factory=lambda: f"exec-appr-{uuid4().hex[:8]}")
    step_id: str = Field(description="Step ID being authorized for execution")
    action_scope: str = Field(default="step_execution", description="Scope of action authorized")
    approved_by_user: bool = Field(default=True, description="Must be explicitly True")
    approved_at: str = Field(description="ISO-8601 timestamp of user approval")
    approval_method: str = Field(default="terminal_prompt", description="How user approved")
    exact_approval_phrase: str = Field(description="Exact phrase or command entered by user")


class FieldActionRecord(BaseModel):
    """Log record of a non-secret field preparation/fill action."""

    model_config = ConfigDict(extra="ignore")

    field_label: str = Field(description="Visible field label or role name")
    approval_id: str = Field(description="User approval record ID for this field fill")
    outcome: str = Field(description="filled, skipped, failed, or manual_required")
    masked_value: str = Field(description="Redacted/masked value displayed for user privacy")


class UserPausePoint(BaseModel):
    """Record of a manual pause event (e.g. CAPTCHA, OTP, Password, manual review)."""

    model_config = ConfigDict(extra="ignore")

    pause_id: str = Field(default_factory=lambda: f"pause-{uuid4().hex[:8]}")
    step_id: str = Field(description="Step ID active during pause")
    reason: str = Field(description="Reason for pause (e.g. CAPTCHA challenge)")
    paused_at: str = Field(description="ISO-8601 timestamp when paused")
    resumed_at: Optional[str] = Field(default=None, description="ISO-8601 timestamp when resumed")
    resume_status: str = Field(default="pending", description="pending, resumed_by_user, cancelled")


class PortalObservation(BaseModel):
    """Observed browser page status from Playwright."""

    model_config = ConfigDict(extra="ignore")

    observation_id: str = Field(default_factory=lambda: f"obs-{uuid4().hex[:8]}")
    page_title: str = Field(description="Visible web page title")
    url: str = Field(description="Current validated allowlisted URL")
    visible_status: str = Field(description="Visible page status summary")
    observed_at: str = Field(description="ISO-8601 timestamp")
    source_type: str = Field(default="playwright_visible_page", description="Observation source")


class StepExecutionResult(BaseModel):
    """Execution result for an individual plan step."""

    model_config = ConfigDict(extra="ignore")

    step_id: str
    status: StepExecutionStatus
    action_summary: str = Field(description="Summary of browser actions taken")
    started_at: str = Field(description="ISO-8601 timestamp")
    completed_at: Optional[str] = Field(default=None, description="ISO-8601 timestamp")
    warnings: List[str] = Field(default_factory=list)


class ExecutionRequest(BaseModel):
    """Public input contract for `execute_approved_steps`."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    execution_request_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str = Field(description="Originating intent request_id")
    intent: IntentResult
    profile_context: ProfileContextResult
    retrieved_evidence: RetrievedEvidenceResult
    workflow_plan: WorkflowPlan
    validation_result: ValidationResult
    selected_step_ids: List[str] = Field(
        default_factory=list,
        description="Explicit step IDs selected for execution in this pass",
    )
    user_approvals: List[UserExecutionApproval] = Field(
        default_factory=list,
        description="Explicit step-scoped approval records collected by orchestrator/CLI",
    )
    confirmed_facts: List[ProfileFact] = Field(
        default_factory=list,
        description="Only confirmed personal facts needed for selected steps",
    )
    starting_url: str = Field(
        default=DEFAULT_STARTING_URL,
        description="Configured official portal starting URL",
    )
    resume_state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Safe, non-secret state for resuming a paused execution",
    )
    dry_run: bool = Field(
        default=False,
        description="When True, browser opens and inspects form but does not mutate or submit",
    )


class ExecutionResult(BaseModel):
    """Canonical output contract of the Execution & Assistance Agent."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    execution_request_id: str = Field(description="Execution request ID")
    request_id: str = Field(description="Originating Intent request_id")
    plan_id: str = Field(description="Workflow plan ID executed")
    plan_version: int = Field(ge=1)
    validation_request_id: str = Field(description="Validated ValidationResult ID")
    execution_status: ExecutionStatus = Field(description="Top-level execution status")
    step_results: List[StepExecutionResult] = Field(default_factory=list)
    field_actions: List[FieldActionRecord] = Field(default_factory=list)
    user_pause_points: List[UserPausePoint] = Field(default_factory=list)
    portal_observations: List[PortalObservation] = Field(default_factory=list)
    approval_records_used: List[str] = Field(default_factory=list)
    submission_attempted: bool = Field(
        default=False,
        description="True if pre-submit marker was written before submission click",
    )
    confirmation_observed: bool = Field(
        default=False,
        description="True ONLY if official portal returned a visible confirmation record",
    )
    confirmation_reference: Optional[str] = Field(
        default=None,
        description="Masked confirmation ID or portal reference text if observed",
    )
    warnings: List[str] = Field(default_factory=list)
    safe_resume_state: Optional[Dict[str, Any]] = Field(default=None)
    completed_at: Optional[str] = Field(default=None)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def execution_result_json_schema() -> dict:
    return ExecutionResult.model_json_schema()


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts" / "execution_result.schema.json"


def write_execution_result_schema(path: Optional[Path] = None) -> Path:
    target = path or default_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(execution_result_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ExecutionResult JSON Schema.")
    parser.add_argument("--out", default=str(default_schema_path()))
    args = parser.parse_args()
    print(f"Wrote {write_execution_result_schema(Path(args.out))}")


if __name__ == "__main__":
    main()
