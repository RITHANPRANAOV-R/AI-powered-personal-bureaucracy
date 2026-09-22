from __future__ import annotations

from typing import Any

from agents.orchestration.intent_understanding.schemas import IntentResult
from agents.orchestration.monitoring.schemas import ChangeDelta, IntentState


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return sorted(str(item) for item in value)
    return value


def _infer_summary_target(summary: str | None) -> str | None:
    if summary is None:
        return None
    lowered = summary.lower()
    if "address" in lowered:
        return "address"
    if "mobile" in lowered or "phone number" in lowered:
        return "mobile_number"
    if "email" in lowered:
        return "email"
    if "name" in lowered:
        return "name"
    if "date of birth" in lowered or "dob" in lowered or "birth date" in lowered:
        return "date_of_birth"
    if "gender" in lowered:
        return "gender"
    if "biometric" in lowered or "fingerprint" in lowered or "iris" in lowered:
        return "biometric"
    return None


def detect_changes(previous: IntentState, new_intent: IntentResult) -> list[ChangeDelta]:
    changes: list[ChangeDelta] = []

    fields = [
        ("intent_type", previous.intent_type, new_intent.intent_type),
        ("update_type", previous.update_type, new_intent.update_type),
        ("summary", previous.summary, new_intent.summary),
        ("urgency", previous.urgency, new_intent.urgency),
        ("confidence", previous.confidence, new_intent.confidence),
    ]

    for field_name, previous_value, new_value in fields:
        previous_n = _normalize_value(previous_value)
        new_n = _normalize_value(new_value)
        if previous_n == new_n:
            continue
        if previous_value is None and new_value is not None:
            changes.append(ChangeDelta(
                field_name=field_name,
                previous_value=previous_value,
                new_value=new_value,
                change_type="field_added",
                reason=f"{field_name} was populated.",
            ))
        elif previous_value is not None and new_value is None:
            changes.append(ChangeDelta(
                field_name=field_name,
                previous_value=previous_value,
                new_value=new_value,
                change_type="field_removed",
                reason=f"{field_name} was cleared.",
            ))
        elif field_name == "intent_type" and previous_value != new_value:
            changes.append(ChangeDelta(
                field_name=field_name,
                previous_value=previous_value,
                new_value=new_value,
                change_type="intent_replaced",
                reason="Intent type changed.",
            ))
        elif field_name == "update_type" and previous_value != new_value:
            changes.append(ChangeDelta(
                field_name=field_name,
                previous_value=previous_value,
                new_value=new_value,
                change_type="intent_replaced",
                reason="Update target changed.",
            ))
        else:
            changes.append(ChangeDelta(
                field_name=field_name,
                previous_value=previous_value,
                new_value=new_value,
                change_type="field_updated",
                reason=f"{field_name} was updated.",
            ))

    previous_entities = {str(item.entity_type): item.value for item in previous.entities}
    new_entities = {str(item.entity_type): item.value for item in new_intent.entities}

    for entity_key, new_value in new_entities.items():
        if entity_key not in previous_entities:
            changes.append(ChangeDelta(
                field_name=entity_key,
                previous_value=None,
                new_value=new_value,
                change_type="field_added",
                reason="New entity was added.",
            ))
        elif previous_entities.get(entity_key) != new_value:
            changes.append(ChangeDelta(
                field_name=entity_key,
                previous_value=previous_entities.get(entity_key),
                new_value=new_value,
                change_type="field_updated",
                reason="Entity value changed.",
            ))

    previous_missing = {item.field_name for item in previous.missing_information}
    new_missing = {item.field_name for item in new_intent.missing_information}
    for field_name in previous_missing - new_missing:
        changes.append(ChangeDelta(
            field_name=field_name,
            previous_value=field_name,
            new_value=None,
            change_type="missing_information_resolved",
            reason="Missing information was resolved.",
        ))

    for field_name in new_missing - previous_missing:
        changes.append(ChangeDelta(
            field_name=field_name,
            previous_value=None,
            new_value=field_name,
            change_type="field_added",
            reason="New missing information was identified.",
        ))

    previous_target = _infer_summary_target(previous.summary)
    new_target = _infer_summary_target(new_intent.summary)
    if previous_target and new_target and previous_target != new_target and previous.intent_type == new_intent.intent_type:
        changes.append(ChangeDelta(
            field_name="summary",
            previous_value=previous.summary,
            new_value=new_intent.summary,
            change_type="contradiction_detected",
            reason="Summary suggests a contradictory Aadhaar field target.",
        ))

    return changes
