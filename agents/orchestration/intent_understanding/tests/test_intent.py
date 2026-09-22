from agents.orchestration.intent_understanding.schemas import IntentRequest
from agents.orchestration.intent_understanding.service import IntentUnderstandingService


def test_update_address_intent():
    request = IntentRequest(session_id="s1", user_message="I want to update my Aadhaar address.")
    result = IntentUnderstandingService().process(request)

    assert result.intent_type == "update"
    assert result.update_type == "address"
    assert "address" in result.summary.lower()
    assert result.confidence > 0.0


def test_change_mobile_number_intent():
    request = IntentRequest(session_id="s2", user_message="I want to change my mobile number.")
    result = IntentUnderstandingService().process(request)

    assert result.intent_type == "update"
    assert result.update_type == "mobile_number"
    assert result.entities


def test_status_inquiry_intent():
    request = IntentRequest(session_id="s3", user_message="I want to check my Aadhaar update status.")
    result = IntentUnderstandingService().process(request)

    assert result.intent_type == "status_inquiry"
    assert result.update_type is None


def test_general_assistance_intent():
    request = IntentRequest(session_id="s4", user_message="I need help with Aadhaar.")
    result = IntentUnderstandingService().process(request)

    assert result.intent_type == "general_assistance"


def test_missing_information_detection():
    request = IntentRequest(session_id="s5", user_message="I want to update my Aadhaar details.")
    result = IntentUnderstandingService().process(request)

    assert any(item.field_name == "update_type" for item in result.missing_information)


def test_entity_extraction():
    request = IntentRequest(session_id="s6", user_message="I want to update my Aadhaar address and email.")
    result = IntentUnderstandingService().process(request)

    entity_types = {item.entity_type for item in result.entities}
    assert "address" in entity_types
    assert "email" in entity_types


def test_unsupported_or_ambiguous_input():
    request = IntentRequest(session_id="s7", user_message="I want to renew my passport.")
    result = IntentUnderstandingService().process(request)

    assert result.intent_type == "general_assistance"


def test_empty_input():
    request = IntentRequest(session_id="s8", user_message="   ")
    result = IntentUnderstandingService().process(request)

    assert result.intent_type == "general_assistance"
    assert result.missing_information


def test_confidence_generation():
    request = IntentRequest(session_id="s9", user_message="I want to update my Aadhaar address.")
    result = IntentUnderstandingService().process(request)

    assert 0.0 <= result.confidence <= 1.0
    assert result.confidence > 0.5
