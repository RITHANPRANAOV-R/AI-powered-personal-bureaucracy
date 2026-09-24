from datetime import datetime, timezone

from agents.orchestration.intent_understanding.schemas import ExtractedEntity, UserRequestInput
from agents.orchestration.intent_understanding.service import IntentUnderstandingService
from agents.orchestration.monitoring.schemas import ChangeDelta, SessionState
from agents.orchestration.monitoring.service import MonitoringService


def _state_from_result(result):
    return SessionState(
        session_id=result.session_id,
        intent_type=result.intent_type,
        update_type=result.update_type,
        summary=result.summary,
        entities=result.entities,
        urgency=result.urgency,
        missing_information=result.missing_information,
        confidence=result.confidence,
        last_updated=datetime.now(timezone.utc),
        version=1,
        change_history=[
            ChangeDelta(
                field_name="status",
                previous_value=None,
                new_value="initial_state",
                change_type="initial_state",
                reason="Initial state created.",
            )
        ],
    )


def test_phase4_basic_integration_success():
    request = UserRequestInput(
        session_id="phase4-basic",
        user_message="I want to update my Aadhaar address.",
    )

    intent_result = IntentUnderstandingService().process(request)

    assert intent_result.intent_type == "update_request"
    assert intent_result.update_type == "address"
    assert intent_result.session_id == "phase4-basic"
    assert any(item.field_name == "new_address" for item in intent_result.missing_information)

    monitored = MonitoringService().process(None, intent_result)
    state = monitored.updated_state

    assert state.session_id == "phase4-basic"
    assert state.intent_type == "update_request"
    assert state.update_type == "address"
    assert state.summary == intent_result.summary
    assert state.entities == intent_result.entities
    assert state.missing_information == intent_result.missing_information
    assert state.confidence == intent_result.confidence
    assert state.version == 1
    assert state.change_history == []


def test_phase4_missing_information_boundary_preserves_details():
    request = UserRequestInput(
        session_id="phase4-missing",
        user_message="I want to update my Aadhaar address.",
    )

    intent_result = IntentUnderstandingService().process(request)
    monitored = MonitoringService().process(None, intent_result)
    state = monitored.updated_state

    assert state.intent_type == intent_result.intent_type == "update_request"
    assert state.update_type == intent_result.update_type == "address"
    assert state.entities == intent_result.entities
    assert state.missing_information == intent_result.missing_information
    assert state.confidence == intent_result.confidence
    assert state.summary == intent_result.summary


def test_phase4_multiturn_integration_resolves_missing_address():
    first = IntentUnderstandingService().process(
        UserRequestInput(session_id="phase4-multiturn", user_message="I want to update my Aadhaar address.")
    )
    assert first.intent_type == "update_request"
    assert first.update_type == "address"

    state_1 = _state_from_result(first)

    second = IntentUnderstandingService().process(
        UserRequestInput(
            session_id="phase4-multiturn",
            user_message="My new address is Coimbatore.",
            current_session_state={"intent_type": first.intent_type, "update_type": first.update_type},
            conversation_history=[first.summary],
        )
    )

    assert second.intent_type == "update_request"
    assert second.update_type == "address"
    assert any(entity.entity_type == "address" and entity.value.lower() == "coimbatore" for entity in second.entities)
    assert second.missing_information == []

    monitored = MonitoringService().process(state_1, second)
    state_2 = monitored.updated_state

    assert state_2.intent_type == "update_request"
    assert state_2.update_type == "address"
    assert state_2.missing_information == []
    assert state_2.version == 2
    assert any(change.change_type == "missing_information_resolved" for change in monitored.changes)
    assert any(change.change_type == "field_updated" for change in monitored.changes)


def test_phase4_target_change_detects_mobile_number_transition():
    first = IntentUnderstandingService().process(
        UserRequestInput(session_id="phase4-target", user_message="I want to update my Aadhaar address.")
    )
    state_1 = _state_from_result(first)

    second = IntentUnderstandingService().process(
        UserRequestInput(
            session_id="phase4-target",
            user_message="Actually, I want to change my mobile number.",
            current_session_state={"intent_type": first.intent_type, "update_type": first.update_type},
        )
    )

    assert second.intent_type == "update_request"
    assert second.update_type == "mobile_number"

    monitored = MonitoringService().process(state_1, second)
    state_2 = monitored.updated_state

    assert state_2.intent_type == "update_request"
    assert state_2.update_type == "mobile_number"
    assert any(change.field_name == "update_type" and change.change_type == "intent_replaced" for change in monitored.changes)
    assert any(change.field_name == "update_type" for change in state_2.change_history)


def test_phase4_status_inquiry_integrates_cleanly():
    request = UserRequestInput(
        session_id="phase4-status",
        user_message="What is the status of my Aadhaar update?",
    )

    intent_result = IntentUnderstandingService().process(request)
    monitored = MonitoringService().process(None, intent_result)
    state = monitored.updated_state

    assert intent_result.intent_type == "status_inquiry"
    assert intent_result.update_type is None
    assert state.intent_type == "status_inquiry"
    assert state.update_type is None
    assert state.version == 1


def test_phase4_correction_request_flow_preserves_canonical_value():
    request = UserRequestInput(
        session_id="phase4-correction",
        user_message="I need to correct my Aadhaar name.",
    )

    intent_result = IntentUnderstandingService().process(request)
    monitored = MonitoringService().process(None, intent_result)
    state = monitored.updated_state

    assert intent_result.intent_type == "correction_request"
    assert intent_result.update_type == "name"
    assert state.intent_type == "correction_request"
    assert state.update_type == "name"
    assert state.summary == intent_result.summary
    assert state.entities == intent_result.entities


def test_phase4_versioning_is_monotonic_across_successive_states():
    first = IntentUnderstandingService().process(
        UserRequestInput(session_id="phase4-version", user_message="I want to update my Aadhaar address.")
    )
    state_1 = _state_from_result(first)

    second = IntentUnderstandingService().process(
        UserRequestInput(
            session_id="phase4-version",
            user_message="My new address is Coimbatore.",
            current_session_state={"intent_type": first.intent_type, "update_type": first.update_type},
            conversation_history=[first.summary],
        )
    )
    state_2 = MonitoringService().process(state_1, second).updated_state

    third = IntentUnderstandingService().process(
        UserRequestInput(
            session_id="phase4-version",
            user_message="Actually, I want to change my mobile number.",
            current_session_state={"intent_type": second.intent_type, "update_type": second.update_type},
        )
    )
    state_3 = MonitoringService().process(state_2, third).updated_state

    assert state_1.version == 1
    assert state_2.version == 2
    assert state_3.version == 3
    assert len(state_3.change_history) >= 1
    assert state_3.intent_type == "update_request"
    assert state_3.update_type == "mobile_number"
