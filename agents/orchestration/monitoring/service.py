from __future__ import annotations

from dataclasses import dataclass, field

from agents.orchestration.intent_understanding.schemas import IntentClassificationResult
from agents.orchestration.monitoring.diff_detector import detect_changes
from agents.orchestration.monitoring.schemas import ChangeDelta, SessionState
from agents.orchestration.monitoring.state_updater import apply_intent_result


@dataclass
class MonitoringResult:
    updated_state: SessionState
    changes: list[ChangeDelta] = field(default_factory=list)

    @property
    def events(self) -> list[ChangeDelta]:
        return self.changes


class MonitoringService:
    def process(self, previous: SessionState | None, intent_result: IntentClassificationResult) -> MonitoringResult:
        changes = detect_changes(previous, intent_result) if previous is not None else []
        updated_state = apply_intent_result(previous, intent_result)
        return MonitoringResult(updated_state=updated_state, changes=changes)


MonitorUpdateService = MonitoringService
