from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agents.orchestration.intent_understanding.schemas import (
    ExtractedEntity,
    IntentClassificationResult,
    UserRequestInput,
)
from agents.orchestration.monitoring.schemas import ChangeDelta, SessionState


def test_valid_user_request_input_creation():
    request = UserRequestInput(
        session_id="session-1",
        user_message="I want to update my Aadhaar address.",
        conversation_history=["I want to update my Aadhaar address."],
        current_session_state={"intent_type": "update_request", "update_type": "address"},
        domain="aadhaar",
    )

    assert request.session_id == "session-1"
    assert request.domain == "aadhaar"


def test_valid_intent_classification_result_creation():
    result = IntentClassificationResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[
            ExtractedEntity(entity_type="address", value="Coimbatore", normalized_value="coimbatore", confidence=0.95)
        ],
        missing_information=[{"field_name": "new_address", "reason": "Address is missing.", "required": True}],
        urgency="normal",
        confidence=0.9,
    )

    assert result.intent_type == "update_request"
    assert result.update_type == "address"
    assert result.confidence == 0.9


def test_valid_session_state_creation():
    state = SessionState(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[
            ExtractedEntity(entity_type="address", value="Coimbatore", normalized_value="coimbatore", confidence=0.95)
        ],
        missing_information=[{"field_name": "new_address", "reason": "Address is missing.", "required": True}],
        confidence=0.8,
        last_updated=datetime.now(timezone.utc),
        version=1,
        change_history=[
            ChangeDelta(
                field_name="update_type",
                previous_value=None,
                new_value="address",
                change_type="field_added",
                reason="Update target identified.",
            )
        ],
    )

    assert state.version == 1
    assert state.last_updated.tzinfo is not None


def test_valid_change_delta_creation():
    delta = ChangeDelta(
        field_name="update_type",
        previous_value=None,
        new_value="mobile_number",
        change_type="intent_replaced",
        reason="Update target changed.",
    )

    assert delta.change_type == "intent_replaced"
    assert delta.new_value == "mobile_number"


def test_missing_required_fields_fail_validation():
    with pytest.raises(ValidationError):
        UserRequestInput(session_id="session-1", user_message="")

    with pytest.raises(ValidationError):
        IntentClassificationResult(
            session_id="session-1",
            intent_type="update_request",
            summary="",
            confidence=0.5,
        )


def test_confidence_below_zero_fails_validation():
    with pytest.raises(ValidationError):
        SessionState(
            session_id="session-1",
            intent_type="status_inquiry",
            summary="Checking status.",
            confidence=-0.1,
            last_updated=datetime.now(timezone.utc),
        )


def test_confidence_above_one_fails_validation():
    with pytest.raises(ValidationError):
        IntentClassificationResult(
            session_id="session-1",
            intent_type="status_inquiry",
            summary="Checking status.",
            confidence=1.1,
        )


def test_session_state_accepts_timezone_aware_datetime():
    state = SessionState(
        session_id="session-1",
        intent_type="status_inquiry",
        summary="Checking status.",
        confidence=0.7,
        last_updated=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
    )

    assert state.last_updated.tzinfo is not None
    assert state.last_updated.utcoffset() == timezone.utc.utcoffset(state.last_updated)


def test_change_history_accepts_change_delta_objects():
    state = SessionState(
        session_id="session-1",
        intent_type="status_inquiry",
        summary="Checking status.",
        confidence=0.7,
        last_updated=datetime.now(timezone.utc),
        change_history=[
            ChangeDelta(
                field_name="intent_type",
                previous_value="update_request",
                new_value="status_inquiry",
                change_type="intent_replaced",
                reason="Status check replaced update flow.",
            )
        ],
    )

    assert len(state.change_history) == 1
    assert state.change_history[0].field_name == "intent_type"


def test_models_serialize_cleanly_to_dict():
    state = SessionState(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        confidence=0.85,
        last_updated=datetime.now(timezone.utc),
        version=2,
    )

    payload = state.model_dump()
    assert payload["session_id"] == "session-1"
    assert payload["intent_type"] == "update_request"
    assert payload["update_type"] == "address"
    assert payload["confidence"] == 0.85


def test_status_inquiry_allows_update_type_none():
    result = IntentClassificationResult(
        session_id="session-1",
        intent_type="status_inquiry",
        update_type=None,
        summary="User wants to check Aadhaar status.",
        confidence=0.8,
    )

    assert result.update_type is None


def test_update_request_requires_update_target():
    result = IntentClassificationResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="mobile_number",
        summary="User wants to update Aadhaar mobile number.",
        confidence=0.8,
    )

    assert result.update_type == "mobile_number"
