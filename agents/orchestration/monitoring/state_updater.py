from __future__ import annotations

from datetime import datetime, timezone

from agents.orchestration.intent_understanding.schemas import IntentClassificationResult
from agents.orchestration.monitoring.diff_detector import detect_changes
from agents.orchestration.monitoring.schemas import SessionState


def apply_intent_result(previous: SessionState | None, current: IntentClassificationResult) -> SessionState:
    if previous is None:
        return SessionState(
            session_id=current.session_id,
            intent_type=current.intent_type,
            update_type=current.update_type,
            summary=current.summary,
            entities=current.entities,
            urgency=current.urgency,
            missing_information=current.missing_information,
            confidence=current.confidence,
            last_updated=datetime.now(timezone.utc),
            version=1,
            change_history=[],
        )

    changes = detect_changes(previous, current)
    if not changes:
        return previous

    return SessionState(
        session_id=current.session_id,
        intent_type=current.intent_type,
        update_type=current.update_type,
        summary=current.summary,
        entities=current.entities,
        urgency=current.urgency,
        missing_information=current.missing_information,
        confidence=current.confidence,
        last_updated=datetime.now(timezone.utc),
        version=previous.version + 1,
        change_history=[*previous.change_history, *changes],
    )
