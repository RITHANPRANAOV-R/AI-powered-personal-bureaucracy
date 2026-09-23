from datetime import datetime, timezone

from agents.orchestration.intent_understanding.schemas import ExtractedEntity, IntentRequest, IntentResult, MissingInformation
from agents.orchestration.monitoring.schemas import IntentState
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
        "last_updated": datetime.now(timezone.utc),
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
    original_update_type = previous.update_type
    original_summary = previous.summary
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
    assert previous.update_type == original_update_type
    assert previous.summary == original_summary


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


def test_state_progression_for_address_then_mobile_number():
    state_1 = build_state(
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        missing_information=[MissingInformation(field_name="new_address", reason="Address update target is specified but not yet provided.", required=True, severity="medium")],
    )
    intent_2 = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="Coimbatore", normalized_value="coimbatore", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.92,
    )
    intent_3 = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="mobile_number",
        summary="User wants to update Aadhaar mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="9876543210", normalized_value="9876543210", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.94,
    )

    result_1 = MonitoringService().process(state_1, intent_2)
    assert result_1.updated_state.update_type == "address"
    assert any(change.field_name == "new_address" and change.change_type == "missing_information_resolved" for change in result_1.changes)

    result_2 = MonitoringService().process(result_1.updated_state, intent_3)
    assert result_2.updated_state.update_type == "mobile_number"
    assert any(change.field_name == "update_type" and change.change_type == "intent_replaced" for change in result_2.changes)
    assert any(event.event_type == "intent_replaced" for event in result_2.events)


def test_public_monitoring_contract_for_downstream_state_consumers():
    initial_state = build_state(
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        missing_information=[MissingInformation(field_name="new_address", reason="Address update target is specified but not yet provided.", required=True, severity="medium")],
    )
    resolved_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="Coimbatore", normalized_value="coimbatore", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.92,
    )
    transition_intent = IntentResult(
        session_id="session-1",
        intent_type="update",
        update_type="mobile_number",
        summary="User wants to update Aadhaar mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="9876543210", normalized_value="9876543210", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.94,
    )

    resolved = MonitoringService().process(initial_state, resolved_intent)
    assert resolved.updated_state.intent_type == "update"
    assert resolved.updated_state.update_type == "address"
    assert any(change.change_type == "missing_information_resolved" for change in resolved.changes)

    transitioned = MonitoringService().process(resolved.updated_state, transition_intent)
    assert transitioned.updated_state.update_type == "mobile_number"
    assert any(change.field_name == "update_type" and change.change_type == "intent_replaced" for change in transitioned.changes)
    assert all(change.field_name != "new_address" for change in transitioned.changes if change.change_type == "field_added")


def test_end_to_end_intent_understanding_and_monitoring_flow():
    from agents.orchestration.intent_understanding.service import IntentUnderstandingService

    message_1 = "I want to update my Aadhaar address."
    result_1 = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session",
        user_message=message_1,
    ))

    assert result_1.intent_type == "update"
    assert result_1.update_type == "address"
    assert any(item.field_name == "new_address" for item in result_1.missing_information)

    state_1 = IntentState(
        session_id=result_1.session_id,
        intent_type=result_1.intent_type,
        update_type=result_1.update_type,
        summary=result_1.summary,
        entities=result_1.entities,
        urgency=result_1.urgency,
        missing_information=result_1.missing_information,
        confidence=result_1.confidence,
        last_updated=datetime.now(timezone.utc),
        version=1,
        change_history=["initial_state"],
    )

    message_2 = "My new address is Coimbatore."
    result_2 = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session",
        user_message=message_2,
    ))

    assert any(entity.entity_type == "address" and entity.value.lower() == "coimbatore" for entity in result_2.entities)
    monitored_2 = MonitoringService().process(state_1, result_2)
    assert monitored_2.updated_state.update_type == "address"
    assert any(change.change_type == "missing_information_resolved" for change in monitored_2.changes)
    assert not any(item.field_name == "new_address" for item in monitored_2.updated_state.missing_information)

    message_3 = "Actually, I want to change my mobile number."
    result_3 = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session",
        user_message=message_3,
    ))

    assert result_3.intent_type == "update"
    assert result_3.update_type == "mobile_number"
    monitored_3 = MonitoringService().process(monitored_2.updated_state, result_3)
    assert monitored_3.updated_state.update_type == "mobile_number"
    assert any(change.field_name == "update_type" and change.change_type == "intent_replaced" for change in monitored_3.changes)

    status_check = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session-status",
        user_message="I want to check my Aadhaar update status.",
    ))
    assert status_check.intent_type == "status_inquiry"
    assert status_check.update_type is None

    status_follow_up = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session-status-2",
        user_message="I updated my address last week, what is the status?",
    ))
    assert status_follow_up.intent_type == "status_inquiry"
    assert status_follow_up.update_type is None
