from __future__ import annotations

from agents.orchestration.intent_understanding.schemas import IntentClassificationResult
from agents.orchestration.monitoring.schemas import ChangeDelta, SessionState


def _entity_map(items):
    return {item.entity_type: item for item in items}


def _target_candidates(summary: str) -> set[str]:
    lowered = summary.lower()
    targets = set()
    if "address" in lowered:
        targets.add("address")
    if "mobile" in lowered or "phone" in lowered:
        targets.add("mobile_number")
    if "email" in lowered:
        targets.add("email")
    if "name" in lowered:
        targets.add("name")
    if "date of birth" in lowered or "dob" in lowered or "birth" in lowered:
        targets.add("date_of_birth")
    if "gender" in lowered:
        targets.add("gender")
    if "biometric" in lowered:
        targets.add("biometric")
    return targets


def detect_changes(previous: SessionState | None, current: IntentClassificationResult) -> list[ChangeDelta]:
    if previous is None:
        return []

    changes: list[ChangeDelta] = []

    if previous.intent_type != current.intent_type:
        changes.append(
            ChangeDelta(
                field_name="intent_type",
                previous_value=previous.intent_type,
                new_value=current.intent_type,
                change_type="intent_replaced",
                reason="Intent type changed from previous turn.",
            )
        )

    if previous.update_type != current.update_type:
        changes.append(
            ChangeDelta(
                field_name="update_type",
                previous_value=previous.update_type,
                new_value=current.update_type,
                change_type="intent_replaced",
                reason="Update target changed from previous turn.",
            )
        )

    if previous.summary != current.summary:
        changes.append(
            ChangeDelta(
                field_name="summary",
                previous_value=previous.summary,
                new_value=current.summary,
                change_type="field_updated",
                reason="Summary changed for the active session.",
            )
        )
        if _target_candidates(previous.summary) and _target_candidates(current.summary) and _target_candidates(previous.summary) != _target_candidates(current.summary):
            changes.append(
                ChangeDelta(
                    field_name="summary",
                    previous_value=previous.summary,
                    new_value=current.summary,
                    change_type="contradiction_detected",
                    reason="Summary now refers to a different Aadhaar field than before.",
                )
            )

    if previous.urgency != current.urgency:
        changes.append(
            ChangeDelta(
                field_name="urgency",
                previous_value=previous.urgency,
                new_value=current.urgency,
                change_type="field_updated",
                reason="Urgency changed.",
            )
        )

    previous_entities = _entity_map(previous.entities)
    current_entities = _entity_map(current.entities)
    for entity_type in sorted(set(previous_entities) | set(current_entities)):
        previous_entity = previous_entities.get(entity_type)
        current_entity = current_entities.get(entity_type)

        if previous_entity is None and current_entity is not None:
            changes.append(
                ChangeDelta(
                    field_name=f"entities.{entity_type}",
                    previous_value=None,
                    new_value=current_entity.value,
                    change_type="field_added",
                    reason=f"Entity {entity_type} was added.",
                )
            )
        elif previous_entity is not None and current_entity is None:
            changes.append(
                ChangeDelta(
                    field_name=f"entities.{entity_type}",
                    previous_value=previous_entity.value,
                    new_value=None,
                    change_type="field_removed",
                    reason=f"Entity {entity_type} was removed.",
                )
            )
        elif previous_entity is not None and current_entity is not None and previous_entity.value != current_entity.value:
            changes.append(
                ChangeDelta(
                    field_name=f"entities.{entity_type}",
                    previous_value=previous_entity.value,
                    new_value=current_entity.value,
                    change_type="field_updated",
                    reason=f"Entity {entity_type} value changed.",
                )
            )

    previous_missing = {item.field_name: item for item in previous.missing_information}
    current_missing = {item.field_name: item for item in current.missing_information}
    for field_name in sorted(set(previous_missing) | set(current_missing)):
        previous_field = previous_missing.get(field_name)
        current_field = current_missing.get(field_name)

        if previous_field is not None and current_field is None:
            target_name = field_name.replace("new_", "")
            if target_name in {"address", "mobile_number", "email", "name", "date_of_birth", "gender", "biometric"} and any(entity.entity_type == target_name for entity in current.entities):
                changes.append(
                    ChangeDelta(
                        field_name=field_name,
                        previous_value=previous_field.model_dump(),
                        new_value=None,
                        change_type="missing_information_resolved",
                        reason=f"Missing information {field_name} was resolved.",
                    )
                )
            else:
                changes.append(
                    ChangeDelta(
                        field_name=f"missing_information.{field_name}",
                        previous_value=previous_field.model_dump(),
                        new_value=None,
                        change_type="missing_information_resolved",
                        reason=f"Missing information {field_name} was resolved.",
                    )
                )
        elif previous_field is None and current_field is not None:
            changes.append(
                ChangeDelta(
                    field_name=f"missing_information.{field_name}",
                    previous_value=None,
                    new_value=current_field.model_dump(),
                    change_type="missing_information_added",
                    reason=f"Missing information {field_name} is now required.",
                )
            )

    if abs(previous.confidence - current.confidence) > 1e-9:
        changes.append(
            ChangeDelta(
                field_name="confidence",
                previous_value=previous.confidence,
                new_value=current.confidence,
                change_type="field_updated",
                reason="Confidence changed.",
            )
        )

    return changes
