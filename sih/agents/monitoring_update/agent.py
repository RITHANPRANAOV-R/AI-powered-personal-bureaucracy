"""Monitoring & Update Agent implementation.

Deterministic state comparison, status event provenance recording, delta detection,
and CLI reminder management.

Zero generative LLM calls are made in this agent.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from datetime import datetime

from pydantic import ValidationError

from agents.compliance_validation.schema import ValidationDecision
from agents.execution_assistance.schema import ExecutionStatus

from .schema import (
    EventSourceType,
    LocalReminder,
    ManualFollowUpInstruction,
    MonitoringRequest,
    MonitoringResult,
    MonitoringStatus,
    PendingAction,
    StateChange,
    StatusEvent,
    StepMonitoringStatus,
    UserReportedUpdate,
    utc_now,
)


class MonitoringAgentError(ValueError):
    """Raised when a monitoring request cannot be parsed or validated."""


class MonitoringUpdateAgent:
    """Public deterministic Monitoring & Update Agent."""

    def update_monitoring_state(self, request: MonitoringRequest) -> MonitoringResult:
        """
        Public callable for updating workflow monitoring state.

        Signature:
            def update_monitoring_state(request: MonitoringRequest) -> MonitoringResult
        """
        try:
            request = MonitoringRequest.model_validate(request)
        except ValidationError as exc:
            raise MonitoringAgentError(f"Invalid MonitoringRequest contract: {exc}") from exc

        warnings: List[str] = []

        # 1. Correlation ID validation
        intent = request.intent
        plan = request.workflow_plan
        val_res = request.validation_result
        exec_res = request.execution_result
        prev_mon = request.previous_monitoring_result

        ids = {
            "intent": intent.request_id,
            "plan": plan.request_id,
            "validation": val_res.request_id,
        }
        if exec_res:
            ids["execution"] = exec_res.request_id
        if prev_mon:
            ids["previous_monitoring"] = prev_mon.request_id

        if len(set(ids.values())) > 1:
            warnings.append(f"Request ID mismatch detected across inputs: {ids}")

        # 2. Build Step Monitoring Statuses & Events
        current_time = request.current_time or utc_now()
        new_events: List[StatusEvent] = []
        step_statuses: List[StepMonitoringStatus] = []
        portal_observed_status: Optional[str] = None
        user_reported_status: Optional[str] = None

        prev_step_map = {s.step_id: s for s in prev_mon.step_statuses} if prev_mon else {}

        for step in plan.steps:
            step_id = step.step_id
            cur_status = step.status.value
            source_type = EventSourceType.PLAN
            source_ref = f"plan:{plan.plan_id}"
            confidence = "verified"
            blocking_reason = step.blocking_reason

            # Validation Agent Overrides
            val_step = next((s for s in val_res.step_results if s.step_id == step_id), None)
            if val_step:
                if val_step.decision.value == "block":
                    cur_status = "blocked"
                    source_type = EventSourceType.VALIDATION_AGENT
                    source_ref = f"validation:{val_res.validation_request_id}"
                    blocking_reason = "; ".join(val_step.reasons)
                elif val_step.decision.value == "needs_user_input":
                    cur_status = "needs_user_input"
                    source_type = EventSourceType.VALIDATION_AGENT
                    source_ref = f"validation:{val_res.validation_request_id}"
                    blocking_reason = "; ".join(val_step.reasons)

            # Execution Agent Overrides
            if exec_res and step_id in request.workflow_plan.steps:
                exec_step = next((s for s in exec_res.step_results if s.step_id == step_id), None)
                if exec_step:
                    if exec_res.confirmation_observed and "portal" in step_id:
                        cur_status = "confirmed"
                        source_type = EventSourceType.OFFICIAL_PORTAL_VISIBLE
                        source_ref = exec_res.confirmation_reference or "official_portal"
                        portal_observed_status = "confirmed"
                    elif exec_res.submission_attempted:
                        cur_status = "submission_attempted"
                        source_type = EventSourceType.EXECUTION_AGENT
                        source_ref = f"execution:{exec_res.execution_request_id}"
                    elif exec_res.execution_status == ExecutionStatus.UNCERTAIN:
                        cur_status = "uncertain"
                        source_type = EventSourceType.EXECUTION_AGENT
                        source_ref = f"execution:{exec_res.execution_request_id}"
                    elif exec_step.status.value == "completed":
                        cur_status = "completed"
                        source_type = EventSourceType.EXECUTION_AGENT
                        source_ref = f"execution:{exec_res.execution_request_id}"

            # User Reported Updates Overrides
            user_upd = next((u for u in request.user_reported_updates if u.step_id == step_id), None)
            if user_upd:
                cur_status = user_upd.reported_status
                source_type = EventSourceType.USER_REPORTED
                source_ref = f"user_update:{user_upd.update_id}"
                confidence = "user_reported"
                user_reported_status = user_upd.reported_status

            # Record StatusEvent
            evt = StatusEvent(
                status_event_id=f"evt-{step_id}-{uuid_short()}",
                step_id=step_id,
                status=cur_status,
                observed_at=current_time,
                source_type=source_type,
                source_reference=source_ref,
                confidence_label=confidence,
                notes=f"Step title: {step.title}",
            )
            new_events.append(evt)

            step_statuses.append(
                StepMonitoringStatus(
                    step_id=step_id,
                    current_status=cur_status,
                    last_updated_at=current_time,
                    last_source_type=source_type,
                    last_event_id=evt.status_event_id,
                    blocking_reason=blocking_reason,
                )
            )

        # 3. Delta Detection (Changes since previous monitoring result)
        changes_detected: List[StateChange] = []
        if prev_mon:
            for cur_s in step_statuses:
                prev_s = prev_step_map.get(cur_s.step_id)
                if not prev_s or prev_s.current_status != cur_s.current_status:
                    changes_detected.append(
                        StateChange(
                            step_id=cur_s.step_id,
                            field_name="status",
                            previous_value=prev_s.current_status if prev_s else None,
                            current_value=cur_s.current_status,
                            changed_at=current_time,
                            source_type=cur_s.last_source_type,
                        )
                    )

        # 4. Pending Actions & Manual Follow-Up Calculation
        pending_actions: List[PendingAction] = []
        for s in step_statuses:
            if s.current_status in {"needs_user_input", "not_started"}:
                pending_actions.append(
                    PendingAction(
                        step_id=s.step_id,
                        action_title=f"Complete step: {s.step_id}",
                        assigned_to="user" if s.current_status == "needs_user_input" else "execution_agent",
                        reason=s.blocking_reason or f"Step status is {s.current_status}.",
                    )
                )
            elif s.current_status in {"submission_attempted", "uncertain"}:
                pending_actions.append(
                    PendingAction(
                        step_id=s.step_id,
                        action_title=f"Manual portal status check for step: {s.step_id}",
                        assigned_to="manual_portal_check",
                        reason="Submission was attempted or outcome is uncertain. Require manual inspection on portal.",
                    )
                )

        manual_follow_up: Optional[ManualFollowUpInstruction] = None
        if any(s.current_status in {"submission_attempted", "uncertain"} for s in step_statuses):
            manual_follow_up = ManualFollowUpInstruction()

        # 5. Local Reminders Calculation
        reminders: List[LocalReminder] = []
        for step in plan.steps:
            if step.status.value == "needs_user_input" or "confirm" in step.step_id:
                reminders.append(
                    LocalReminder(
                        reminder_id=f"rem-{step.step_id}",
                        step_id=step.step_id,
                        due_at=current_time,
                        timezone=request.user_timezone or "UTC",
                        message=f"Reminder: Action required for step '{step.title}'",
                        source_evidence_ids=list(step.evidence_ids),
                        is_due=True,
                        is_overdue=False,
                    )
                )

        # 6. Workflow & Monitoring Status Determination
        workflow_status = _determine_workflow_status(step_statuses, exec_res)
        monitoring_status = _determine_monitoring_status(
            workflow_status, changes_detected, step_statuses, prev_mon
        )

        exec_req_id = exec_res.execution_request_id if exec_res else None

        return MonitoringResult(
            contract_version="1.0",
            monitoring_request_id=request.monitoring_request_id,
            request_id=intent.request_id,
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            execution_request_id=exec_req_id,
            monitoring_status=monitoring_status,
            workflow_status=workflow_status,
            step_statuses=step_statuses,
            status_events=new_events,
            changes_detected=changes_detected,
            pending_actions=pending_actions,
            manual_follow_up=manual_follow_up,
            reminders=reminders,
            portal_observed_status=portal_observed_status,
            user_reported_status=user_reported_status,
            warnings=warnings,
            updated_at=current_time,
        )


def _determine_workflow_status(
    step_statuses: List[StepMonitoringStatus],
    exec_res: Optional[ExecutionResult],
) -> str:
    statuses = {s.current_status for s in step_statuses}
    if "confirmed" in statuses or (exec_res and exec_res.confirmation_observed):
        return "confirmed"
    if "submission_attempted" in statuses:
        return "submission_attempted"
    if "uncertain" in statuses:
        return "uncertain"
    if "blocked" in statuses:
        return "blocked"
    if "needs_user_input" in statuses:
        return "needs_user_input"
    if "completed" in statuses:
        return "completed"
    return "in_progress"


def _determine_monitoring_status(
    workflow_status: str,
    changes: List[StateChange],
    step_statuses: List[StepMonitoringStatus],
    prev_mon: Optional[MonitoringResult],
) -> MonitoringStatus:
    if workflow_status == "uncertain":
        return MonitoringStatus.UNCERTAIN
    if workflow_status == "blocked":
        return MonitoringStatus.BLOCKED
    if any(s.current_status in {"submission_attempted", "uncertain"} for s in step_statuses):
        return MonitoringStatus.MANUAL_CHECK_REQUIRED
    if any(s.current_status == "needs_user_input" for s in step_statuses):
        return MonitoringStatus.NEEDS_USER_UPDATE
    if changes:
        return MonitoringStatus.CHANGED
    return MonitoringStatus.CURRENT


def update_monitoring_state(request: MonitoringRequest) -> MonitoringResult:
    """Public callable interface for Monitoring & Update Agent."""
    return MonitoringUpdateAgent().update_monitoring_state(request)


def uuid_short() -> str:
    import uuid
    return uuid.uuid4().hex[:8]
