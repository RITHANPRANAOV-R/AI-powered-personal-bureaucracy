from __future__ import annotations

from datetime import datetime

from agents.orchestration.intent_understanding.schemas import IntentResult
from agents.orchestration.monitoring.schemas import ChangeDelta, IntentState


def apply_changes(previous: IntentState, changes: list[ChangeDelta], new_intent: IntentResult) -> IntentState:
    updated = previous.model_copy(deep=True)

    updated.intent_type = new_intent.intent_type
    updated.update_type = new_intent.update_type
    updated.summary = new_intent.summary
    updated.entities = new_intent.entities
    updated.urgency = new_intent.urgency
    updated.missing_information = new_intent.missing_information
    updated.confidence = new_intent.confidence
    updated.last_updated = datetime.utcnow()
    updated.version = previous.version + 1

    if isinstance(updated.change_history, list):
        updated.change_history = [*updated.change_history, "state_updated"]

    return updated
