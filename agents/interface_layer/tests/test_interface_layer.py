import pytest
from pydantic import ValidationError

from agents.interface_layer.schemas import InterfaceRequest, InterfaceResponse


def test_valid_request():
    request = InterfaceRequest(
        session_id="session-123",
        user_message="I need to update my Aadhaar address.",
        conversation_history=["Hi", "I want to update my Aadhaar address."],
        current_session_state={"intent": "update_request"},
    )

    assert request.session_id == "session-123"
    assert request.domain == "aadhaar"
    assert request.user_message == "I need to update my Aadhaar address."
    assert request.conversation_history == ["Hi", "I want to update my Aadhaar address."]
    assert request.current_session_state == {"intent": "update_request"}


def test_missing_session_id():
    with pytest.raises(ValidationError):
        InterfaceRequest(session_id="", user_message="I need help with Aadhaar.")


def test_empty_user_message():
    with pytest.raises(ValidationError):
        InterfaceRequest(session_id="session-456", user_message="   ")


def test_default_domain():
    request = InterfaceRequest(session_id="session-789", user_message="Check my Aadhaar status.")
    assert request.domain == "aadhaar"


def test_optional_conversation_history():
    request = InterfaceRequest(session_id="session-000", user_message="Need help")
    assert request.conversation_history is None


def test_optional_session_state():
    request = InterfaceRequest(session_id="session-111", user_message="Need help")
    assert request.current_session_state is None


def test_invalid_request_handling():
    response = InterfaceResponse(
        session_id="session-001",
        accepted=False,
        valid=False,
        error_message="session_id is required",
    )

    assert response.session_id == "session-001"
    assert response.accepted is False
    assert response.valid is False
    assert response.error_message == "session_id is required"
