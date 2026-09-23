"""Pydantic contracts for the Monitoring & Update Agent.

Upstream contracts IntentResult, WorkflowPlan, ValidationResult, and ExecutionResult
are imported unchanged from their respective packages.
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
from agents.execution_assistance.schema import ExecutionResult
from agents.intent_understanding.schema import IntentResult
from agents.workflow_planning.schema import WorkflowPlan


CONTRACT_VERSION = "1.0"


class MonitoringStatus(str, Enum):
    CURRENT = "current"
    CHANGED = "changed"
    NEEDS_USER_UPDATE = "needs_user_update"
    MANUAL_CHECK_REQUIRED = "manual_check_required"
    UNCERTAIN = "uncertain"
    BLOCKED = "blocked"
    FAILED = "failed"


class EventSourceType(str, Enum):
    PLAN = "plan"
    VALIDATION_AGENT = "validation_agent"
    EXECUTION_AGENT = "execution_agent"
    OFFICIAL_PORTAL_VISIBLE = "official_portal_visible"
    USER_REPORTED = "user_reported"


class UserReportedUpdate(BaseModel):
    """User-reported status update for a specific workflow step."""

    model_config = ConfigDict(extra="ignore")

    update_id: str = Field(default_factory=lambda: f"user-upd-{uuid4().hex[:8]}")
    step_id: str = Field(description="Step ID being updated by user")
    reported_status: str = Field(description="User-reported status (e.g., completed, in_progress, pending)")
    user_notes: str = Field(default="", description="User notes or portal observation comments")
    reported_at: str = Field(description="ISO-8601 timestamp when user entered the update")


class ReminderPreferences(BaseModel):
    """Preferences for local CLI reminder evaluations."""

    model_config = ConfigDict(extra="ignore")

    enable_reminders: bool = True
    default_lead_days: int = Field(default=1, ge=0)


class StatusEvent(BaseModel):
    """Individual timestamped workflow status event with explicit provenance."""

    model_config = ConfigDict(extra="ignore")

    status_event_id: str = Field(default_factory=lambda: f"evt-{uuid4().hex[:8]}")
    step_id: str = Field(description="Step ID or 'workflow_level' for overall plan status")
    status: str = Field(description="Status value (e.g. ready, in_progress, submission_attempted, confirmed)")
    observed_at: str = Field(description="ISO-8601 timestamp of observation")
    source_type: EventSourceType = Field(description="Explicit provenance source")
    source_reference: str = Field(description="Step/result/URL reference for traceability")
    confidence_label: str = Field(default="verified", description="verified, user_reported, or unconfirmed")
    notes: str = Field(default="", description="Non-secret detail note")


class StepMonitoringStatus(BaseModel):
    """Current per-step monitoring status record."""

    model_config = ConfigDict(extra="ignore")

    step_id: str
    current_status: str = Field(description="Current validated status for this step")
    last_updated_at: str = Field(description="ISO-8601 timestamp of last update")
    last_source_type: EventSourceType = Field(description="Source of last update")
    last_event_id: str = Field(description="ID of corresponding StatusEvent")
    blocking_reason: Optional[str] = Field(default=None, description="Blocking reason if blocked")


class StateChange(BaseModel):
    """Change detected since previous monitoring pass."""

    model_config = ConfigDict(extra="ignore")

    step_id: str
    field_name: str = Field(description="Field or status property changed")
    previous_value: Optional[str] = Field(default=None)
    current_value: str
    changed_at: str = Field(description="ISO-8601 timestamp")
    source_type: EventSourceType


class PendingAction(BaseModel):
    """Outstanding task requiring user or system attention."""

    model_config = ConfigDict(extra="ignore")

    step_id: str
    action_title: str
    assigned_to: str = Field(description="user, execution_agent, or manual_portal_check")
    reason: str


class ManualFollowUpInstruction(BaseModel):
    """Instructions for user-initiated manual portal status checking."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="Check Official Portal Application Status")
    portal_name: str = Field(default="Passport Seva Official Portal")
    official_url: str = Field(default="https://services2.passportindia.gov.in/forms/")
    instructions: str = Field(
        default="Visit the official portal manually, log in or enter your ARN, complete the CAPTCHA, and view status."
    )
    required_user_inputs: List[str] = Field(
        default_factory=lambda: ["ARN / Application File Number", "Date of Birth", "Manual CAPTCHA"],
        description="Non-stored inputs user must complete manually on portal",
    )


class LocalReminder(BaseModel):
    """Local CLI reminder for pending follow-ups or deadlines."""

    model_config = ConfigDict(extra="ignore")

    reminder_id: str = Field(default_factory=lambda: f"rem-{uuid4().hex[:8]}")
    step_id: str
    due_at: str = Field(description="ISO-8601 timestamp when reminder is due")
    timezone: str = Field(default="UTC")
    message: str = Field(description="Reminder message for display in CLI")
    source_evidence_ids: List[str] = Field(default_factory=list)
    is_due: bool = False
    is_overdue: bool = False


class MonitoringRequest(BaseModel):
    """Public input contract for `update_monitoring_state`."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    monitoring_request_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str = Field(description="Originating intent request_id")
    intent: IntentResult
    workflow_plan: WorkflowPlan
    validation_result: ValidationResult
    execution_result: Optional[ExecutionResult] = Field(default=None)
    previous_monitoring_result: Optional[MonitoringResult] = Field(default=None)
    user_reported_updates: List[UserReportedUpdate] = Field(default_factory=list)
    current_time: str = Field(default_factory=lambda: utc_now())
    user_timezone: Optional[str] = Field(default=None, description="User timezone (e.g. UTC, Asia/Kolkata)")
    reminder_preferences: Optional[ReminderPreferences] = Field(default=None)


class MonitoringResult(BaseModel):
    """Canonical output contract of the Monitoring & Update Agent."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    monitoring_request_id: str = Field(description="Monitoring request ID")
    request_id: str = Field(description="Originating Intent request_id")
    plan_id: str = Field(description="Workflow plan ID monitored")
    plan_version: int = Field(ge=1)
    execution_request_id: Optional[str] = Field(default=None)
    monitoring_status: MonitoringStatus = Field(description="Top-level monitoring status")
    workflow_status: str = Field(description="Validated summary status of overall workflow")
    step_statuses: List[StepMonitoringStatus] = Field(default_factory=list)
    status_events: List[StatusEvent] = Field(default_factory=list)
    changes_detected: List[StateChange] = Field(default_factory=list)
    pending_actions: List[PendingAction] = Field(default_factory=list)
    manual_follow_up: Optional[ManualFollowUpInstruction] = Field(default=None)
    reminders: List[LocalReminder] = Field(default_factory=list)
    portal_observed_status: Optional[str] = Field(
        default=None,
        description="Nullable status ONLY when directly observed from official allowlisted page",
    )
    user_reported_status: Optional[str] = Field(
        default=None,
        description="Nullable separately labeled user report",
    )
    warnings: List[str] = Field(default_factory=list)
    updated_at: str = Field(description="ISO-8601 timestamp with timezone")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def monitoring_result_json_schema() -> dict:
    return MonitoringResult.model_json_schema()


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts" / "monitoring_result.schema.json"


def write_monitoring_result_schema(path: Optional[Path] = None) -> Path:
    target = path or default_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(monitoring_result_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MonitoringResult JSON Schema.")
    parser.add_argument("--out", default=str(default_schema_path()))
    args = parser.parse_args()
    print(f"Wrote {write_monitoring_result_schema(Path(args.out))}")


if __name__ == "__main__":
    main()
