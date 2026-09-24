from __future__ import annotations

from dataclasses import dataclass, field

from agents.orchestration.intent_understanding.schemas import IntentClassificationResult
from agents.orchestration.monitoring.diff_detector import detect_changes
from agents.orchestration.monitoring.schemas import ChangeDelta, MonitoringApplicationInput, MonitoringEvent, SessionState
from agents.orchestration.monitoring.state_updater import apply_intent_result


@dataclass
class MonitoringResult:
    updated_state: SessionState
    changes: list[ChangeDelta] = field(default_factory=list)

    @property
    def events(self) -> list[ChangeDelta]:
        return self.changes


class MonitoringService:
    @staticmethod
    def _is_document_requirement(state: MonitoringApplicationInput) -> bool:
        text = " ".join(
            part for part in [
                state.current_status,
                state.required_action or "",
                state.pending_action or "",
                state.service_type,
            ] if part
        ).lower()
        return (
            "document" in text
            or "proof" in text
            or "upload" in text
            or state.current_status == "pending_document"
        )

    @staticmethod
    def _is_correction_requirement(state: MonitoringApplicationInput) -> bool:
        text = " ".join(
            part for part in [
                state.current_status,
                state.required_action or "",
                state.pending_action or "",
            ] if part
        ).lower()
        return (
            "correction" in text
            or "correct" in text
            or "mismatch" in text
            or "fix" in text
        )

    @staticmethod
    def _is_workflow_blocked(state: MonitoringApplicationInput) -> bool:
        text = " ".join(
            part for part in [state.current_status, state.required_action or "", state.pending_action or ""] if part
        ).lower()
        return (
            "workflow_failed" in text
            or "blocked" in text
            or "failed" in text
            or "rejected" in text
        )

    @staticmethod
    def _is_completed(state: MonitoringApplicationInput) -> bool:
        text = " ".join(part for part in [state.current_status, state.pending_action or ""] if part).lower()
        return "completed" in text or "approved" in text

    @classmethod
    def _emit_event(
        cls,
        previous: MonitoringApplicationInput | None,
        current: MonitoringApplicationInput,
        event_type: str,
        reason: str,
        severity: str = "medium",
        priority: str = "normal",
        metadata: dict | None = None,
    ) -> MonitoringEvent:
        return MonitoringEvent(
            application_id=current.application_id,
            service_id=current.service_id,
            service_type=current.service_type,
            current_status=current.current_status,
            previous_status=previous.current_status if previous is not None else None,
            timestamp=current.timestamp,
            required_action=current.required_action,
            pending_action=current.pending_action,
            source=current.source,
            event_type=event_type,
            severity=severity,
            priority=priority,
            detected_at=current.detected_at,
            metadata={"reason": reason, **(metadata or {})},
        )

    @classmethod
    def detect_events(
        cls,
        previous: MonitoringApplicationInput | None,
        current: MonitoringApplicationInput,
    ) -> list[MonitoringEvent]:
        if current is None:
            return []

        if previous is None:
            events: list[MonitoringEvent] = []
            if current.current_status:
                events.append(cls._emit_event(previous, current, "status_changed", "Application status was initialized or first observed."))
            if current.required_action:
                events.append(cls._emit_event(previous, current, "required_action_detected", "Required user action identified."))
            if cls._is_document_requirement(current):
                events.append(cls._emit_event(previous, current, "document_required", "Document requirement identified."))
            if cls._is_correction_requirement(current):
                events.append(cls._emit_event(previous, current, "correction_required", "Correction requirement identified."))
            if cls._is_workflow_blocked(current):
                events.append(cls._emit_event(previous, current, "workflow_blocked", "Application workflow is blocked or failed."))
            if cls._is_completed(current):
                events.append(cls._emit_event(previous, current, "completed", "Application is completed."))
            return events

        if previous == current:
            return []

        events: list[MonitoringEvent] = []
        if previous.current_status != current.current_status:
            events.append(cls._emit_event(previous, current, "status_changed", "Application status changed."))
        if previous.required_action != current.required_action and current.required_action:
            events.append(cls._emit_event(previous, current, "required_action_detected", "Required user action detected."))
        if cls._is_document_requirement(current) and not cls._is_document_requirement(previous):
            events.append(cls._emit_event(previous, current, "document_required", "Document requirement detected."))
        if cls._is_correction_requirement(current) and not cls._is_correction_requirement(previous):
            events.append(cls._emit_event(previous, current, "correction_required", "Correction requirement detected."))
        if cls._is_workflow_blocked(current) and not cls._is_workflow_blocked(previous):
            events.append(cls._emit_event(previous, current, "workflow_blocked", "Workflow is blocked or failed."))
        if cls._is_completed(current) and not cls._is_completed(previous):
            events.append(cls._emit_event(previous, current, "completed", "Application completed."))
        return events

    def process(self, previous: SessionState | MonitoringApplicationInput | None, intent_result: IntentClassificationResult | MonitoringApplicationInput | None) -> MonitoringResult | list[MonitoringEvent]:
        if isinstance(previous, MonitoringApplicationInput) and isinstance(intent_result, MonitoringApplicationInput):
            return self.detect_events(previous, intent_result)

        changes = detect_changes(previous, intent_result) if previous is not None else []
        updated_state = apply_intent_result(previous, intent_result)
        return MonitoringResult(updated_state=updated_state, changes=changes)


MonitorUpdateService = MonitoringService
