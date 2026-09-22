from datetime import datetime

from agents.orchestration.intent_understanding.schemas import ExtractedEntity, IntentResult, MissingInformation
from agents.orchestration.monitoring.schemas import IntentState, MonitoringEvent
from agents.orchestration.monitoring.service import MonitoringService


def build_state(**kwargs):
    default = {
        "session_id": "session-1",
        "intent_type": "update",
        "update_type": "address",
        "summary": "User wants to update Aadhaar address.",
        "entities": [ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)],
        "urgency": "normal",
        "missing_information": [],
        "confidence": 0.85,
        "last_updated": datetime.utcnow(),
        "version": 1,
        "change_history": ["initial_state"],
    }
    default.update(kwargs)
    return IntentState(**default)


def test_no_change():
    previous = build_state()
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.85,
    )

    result = MonitoringService().process(previous, new_intent)
    assert result.changes == []
    assert result.updated_state.intent_type == "update"


def test_address_update():
    previous = build_state()
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.90,
    )

    result = MonitoringService().process(previous, new_intent)
    assert len(result.changes) >= 1
    assert any(change.field_name == "confidence" for change in result.changes)


def test_mobile_number_update():
    previous = build_state(update_type="address")
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="mobile_number",
        summary="User wants to update mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.88,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.change_type == "intent_replaced" for change in result.changes)
    assert any(change.field_name == "update_type" for change in result.changes)


def test_new_entity_added():
    previous = build_state(entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)])
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address and email.",
        entities=[
            ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9),
            ExtractedEntity(entity_type="email", value="email", normalized_value="email", confidence=0.8),
        ],
        urgency="normal",
        missing_information=[],
        confidence=0.93,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.change_type == "field_added" for change in result.changes)


def test_missing_information_resolved():
    previous = build_state(missing_information=[MissingInformation(field_name="update_type", reason="Not specified", required=True, severity="medium")])
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.91,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.change_type == "missing_information_resolved" for change in result.changes)


def test_intent_replacement():
    previous = build_state(intent_type="status_inquiry", update_type=None)
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="mobile_number",
        summary="User now wants to update mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.9,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.field_name == "intent_type" for change in result.changes)


def test_contradictory_values():
    previous = build_state(summary="User wants to update Aadhaar address.")
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.9,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.change_type == "contradiction_detected" for change in result.changes)


def test_multiple_changes_in_one_message():
    previous = build_state(
        missing_information=[MissingInformation(field_name="update_type", reason="Not specified", required=True, severity="medium")],
        confidence=0.7,
    )
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[
            ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9),
            ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.8),
        ],
        urgency="normal",
        missing_information=[],
        confidence=0.95,
    )

    result = MonitoringService().process(previous, new_intent)
    assert len(result.changes) >= 3


def test_previous_state_not_mutated():
    previous = build_state()
    original_version = previous.version
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="mobile_number",
        summary="User wants to update mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.92,
    )

    MonitoringService().process(previous, new_intent)
    assert previous.version == original_version
    assert previous.update_type == "address"


def test_state_history_is_preserved():
    previous = build_state(change_history=["initial_state", "first_update"]) 
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.9,
    )

    result = MonitoringService().process(previous, new_intent)
    assert len(result.updated_state.change_history) >= 2
    assert "initial_state" in result.updated_state.change_history
