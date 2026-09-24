import pytest
from pydantic import ValidationError

from agents.interface_layer.schemas import InterfaceRequest, InterfaceResponse
from agents.interface_layer.service import InterfaceService


def test_valid_request():
    request = InterfaceRequest(
        session_id="session-1",
        user_message="I need help with Aadhaar.",
        conversation_history=["Hi", "I need help with Aadhaar."],
        current_session_state={"last_intent": "update_request"},
    )

    response = InterfaceService().process(request)

    assert response.accepted is True
    assert response.valid is True
    assert response.session_id == "session-1"
    assert response.error_message is None
    assert response.downstream_payload == {
        "session_id": "session-1",
        "user_message": "I need help with Aadhaar.",
        "domain": "aadhaar",
        "conversation_history": ["Hi", "I need help with Aadhaar."],
        "current_session_state": {"last_intent": "update_request"},
    }


def test_preservation_of_session_id():
    response = InterfaceService().process({
        "session_id": "session-preserve",
        "user_message": "Check my status.",
    })

    assert response.session_id == "session-preserve"
    assert response.downstream_payload["session_id"] == "session-preserve"


def test_preservation_of_user_message():
    request = InterfaceRequest(session_id="session-2", user_message="Update my Aadhaar address.")
    response = InterfaceService().process(request)

    assert response.downstream_payload["user_message"] == "Update my Aadhaar address."


def test_default_domain():
    response = InterfaceService().process({"session_id": "session-3", "user_message": "Need help"})

    assert response.accepted is True
    assert response.downstream_payload["domain"] == "aadhaar"


def test_conversation_history_passthrough():
    history = ["Hello", "I want to update my Aadhaar address."]
    response = InterfaceService().process({
        "session_id": "session-4",
        "user_message": "I want to update my Aadhaar address.",
        "conversation_history": history,
    })

    assert response.downstream_payload["conversation_history"] == history


def test_current_session_state_passthrough():
    state = {"intent": "status_inquiry", "confidence": 0.8}
    response = InterfaceService().process({
        "session_id": "session-5",
        "user_message": "Check my status.",
        "current_session_state": state,
    })

    assert response.downstream_payload["current_session_state"] == state


def test_invalid_request_handling():
    response = InterfaceService().process({"session_id": "", "user_message": ""})

    assert response.accepted is False
    assert response.valid is False
    assert response.downstream_payload is None
    assert response.error_message is not None
    assert response.session_id == "invalid"


def test_no_downstream_agent_invocation():
    request = InterfaceRequest(session_id="session-6", user_message="Test only")
    response = InterfaceService().process(request)

    assert response.downstream_payload is not None
    assert "agent" not in response.downstream_payload
    assert response.downstream_payload["user_message"] == "Test only"


def test_public_imports_and_contract_are_available():
    from agents.interface_layer import InterfaceRequest as PublicRequest
    from agents.interface_layer import InterfaceResponse as PublicResponse
    from agents.interface_layer import InterfaceService as PublicService

    request = PublicRequest(session_id="session-7", user_message="Need help")
    response = PublicService().process(request)

    assert isinstance(request, PublicRequest)
    assert isinstance(response, PublicResponse)
    assert response.valid is True
    assert response.downstream_payload["session_id"] == "session-7"


def test_future_downstream_consumer_can_use_normalized_payload_without_downstream_imports():
    response = InterfaceService().process({
        "session_id": "session-8",
        "user_message": "I need help with Aadhaar.",
        "domain": "aadhaar",
        "conversation_history": ["Hello"],
        "current_session_state": {"last_status": "ready"},
    })

    payload = response.downstream_payload
    assert payload.keys() == {"session_id", "user_message", "domain", "conversation_history", "current_session_state"}
    assert payload["session_id"] == "session-8"
    assert payload["user_message"] == "I need help with Aadhaar."
    assert payload["conversation_history"] == ["Hello"]
    assert payload["current_session_state"] == {"last_status": "ready"}
    assert "IntentClassificationResult" not in str(payload)
