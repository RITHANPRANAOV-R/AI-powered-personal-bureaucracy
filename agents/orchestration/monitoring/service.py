from __future__ import annotations

import uuid
from datetime import datetime

from agents.orchestration.intent_understanding.schemas import IntentResult
from agents.orchestration.monitoring.diff_detector import detect_changes
from agents.orchestration.monitoring.schemas import IntentState, MonitoringEvent, UpdateResult
from agents.orchestration.monitoring.state_updater import apply_changes


class MonitoringService:
    def process(self, previous: IntentState, new_intent: IntentResult) -> UpdateResult:
        changes = detect_changes(previous, new_intent)
        updated_state = apply_changes(previous, changes, new_intent)

        events = [
            MonitoringEvent(
                event_id=str(uuid.uuid4()),
                session_id=updated_state.session_id,
                event_type=change.change_type,
                timestamp=datetime.utcnow(),
                intent_type=updated_state.intent_type,
                payload={"field_name": change.field_name, "reason": change.reason},
            )
            for change in changes
        ]

        return UpdateResult(
            session_id=updated_state.session_id,
            changes=changes,
            updated_state=updated_state,
            events=events,
        )
