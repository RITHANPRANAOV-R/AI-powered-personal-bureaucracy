from agents.orchestration.intent_understanding.schemas import UserRequestInput
from agents.orchestration.intent_understanding.service import IntentUnderstandingService


service = IntentUnderstandingService()


def test_update_address_intent():
    request = UserRequestInput(session_id="s1", user_message="I want to update my Aadhaar address.")
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "address"
    assert "address" in result.summary.lower()
    assert result.confidence > 0.0


def test_correction_address_intent():
    request = UserRequestInput(session_id="s2", user_message="I want to correct my Aadhaar address.")
    result = service.process(request)

    assert result.intent_type == "correction_request"
    assert result.update_type == "address"


def test_status_inquiry_intent():
    request = UserRequestInput(session_id="s3", user_message="I want to check my Aadhaar update status.")
    result = service.process(request)

    assert result.intent_type == "status_inquiry"
    assert result.update_type is None


def test_complaint_intent():
    request = UserRequestInput(session_id="s4", user_message="I have a problem with my Aadhaar.")
    result = service.process(request)

    assert result.intent_type == "complaint"


def test_general_assistance_intent():
    request = UserRequestInput(session_id="s5", user_message="I need help with Aadhaar.")
    result = service.process(request)

    assert result.intent_type == "general_assistance"


def test_explicit_address_extraction():
    request = UserRequestInput(session_id="s6", user_message="My new address is Coimbatore.")
    result = service.process(request)

    assert any(entity.entity_type == "address" and entity.value.lower() == "coimbatore" for entity in result.entities)
    assert result.update_type == "address"


def test_mobile_target():
    request = UserRequestInput(session_id="s7", user_message="I want to change my mobile number.")
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "mobile_number"
    assert any(item.field_name == "new_mobile_number" for item in result.missing_information)


def test_missing_update_target():
    request = UserRequestInput(session_id="s8", user_message="I want to update my Aadhaar.")
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "unknown"
    assert any(item.field_name == "update_type" for item in result.missing_information)


def test_missing_address_value():
    request = UserRequestInput(session_id="s9", user_message="I want to update my Aadhaar address.")
    result = service.process(request)

    assert result.update_type == "address"
    assert any(item.field_name == "new_address" for item in result.missing_information)


def test_status_does_not_request_update_value():
    request = UserRequestInput(session_id="s10", user_message="I want to check my Aadhaar update status.")
    result = service.process(request)

    assert result.intent_type == "status_inquiry"
    assert result.missing_information == []


def test_multiturn_continuation_uses_context():
    first = UserRequestInput(session_id="s11", user_message="I want to update my Aadhaar address.")
    first_result = service.process(first)
    assert first_result.update_type == "address"

    follow_up = UserRequestInput(
        session_id="s11",
        user_message="My new address is Coimbatore.",
        current_session_state={"intent_type": "update_request", "update_type": "address"},
    )
    second_result = service.process(follow_up)

    assert second_result.intent_type == "update_request"
    assert second_result.update_type == "address"
    assert any(entity.entity_type == "address" and entity.value.lower() == "coimbatore" for entity in second_result.entities)
    assert not any(item.field_name == "new_address" for item in second_result.missing_information)


def test_target_replacement_uses_latest_target():
    first = UserRequestInput(session_id="s12", user_message="I want to update my Aadhaar address.")
    first_result = service.process(first)
    assert first_result.update_type == "address"

    second = UserRequestInput(
        session_id="s12",
        user_message="Actually, I want to change my mobile number.",
        current_session_state={"intent_type": "update_request", "update_type": "address"},
    )
    second_result = service.process(second)

    assert second_result.intent_type == "update_request"
    assert second_result.update_type == "mobile_number"


def test_ambiguous_request_has_lower_confidence():
    request = UserRequestInput(session_id="s13", user_message="I want to update my Aadhaar.")
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "unknown"
    assert result.confidence < 0.8


def test_entity_extraction_does_not_invent_values():
    request = UserRequestInput(session_id="s14", user_message="I want to update my Aadhaar.")
    result = service.process(request)

    assert result.entities == []
    assert result.update_type == "unknown"


def test_explicit_email_extraction_is_supported():
    request = UserRequestInput(session_id="s15", user_message="My email is user@example.com.")
    result = service.process(request)

    assert any(entity.entity_type == "email" and entity.value == "user@example.com" for entity in result.entities)


def test_update_target_is_resolved_from_context_when_no_target_in_message():
    request = UserRequestInput(
        session_id="s16",
        user_message="My new address is Coimbatore.",
        current_session_state={"intent_type": "update_request", "update_type": "address"},
    )
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "address"
    assert any(entity.entity_type == "address" and entity.value.lower() == "coimbatore" for entity in result.entities)
    assert not any(item.field_name == "new_address" for item in result.missing_information)


def test_document_request_intent():
    request = UserRequestInput(session_id="s17", user_message="I need my Aadhaar card copy.")
    result = service.process(request)

    assert result.intent_type == "document_request"


def test_enrollment_intent():
    request = UserRequestInput(session_id="s18", user_message="I want to enroll for Aadhaar.")
    result = service.process(request)

    assert result.intent_type == "enrollment"


def test_biometric_target_intent():
    request = UserRequestInput(session_id="s19", user_message="I want to update my biometric data.")
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "biometric"


def test_date_of_birth_correction_target():
    request = UserRequestInput(session_id="s20", user_message="I want to correct my date of birth.")
    result = service.process(request)

    assert result.intent_type == "correction_request"
    assert result.update_type == "date_of_birth"


def test_gender_target_intent():
    request = UserRequestInput(session_id="s21", user_message="Please update my gender.")
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "gender"


def test_name_target_intent():
    request = UserRequestInput(session_id="s22", user_message="I want to change my name.")
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "name"


def test_email_update_target_intent():
    request = UserRequestInput(session_id="s23", user_message="I want to update my Aadhaar email.")
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "email"
    assert any(item.field_name == "new_email" for item in result.missing_information)


def test_conversation_history_continuation_extracts_address_from_context():
    request = UserRequestInput(
        session_id="s24",
        user_message="My new address is Coimbatore.",
        conversation_history=["I want to update my Aadhaar address."],
    )
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "address"
    assert any(entity.entity_type == "address" and entity.value.lower() == "coimbatore" for entity in result.entities)
    assert not any(item.field_name == "new_address" for item in result.missing_information)


def test_conversation_history_target_context_for_mobile_number():
    request = UserRequestInput(
        session_id="s25",
        user_message="My new number is 9876543210.",
        conversation_history=["I want to update my Aadhaar mobile number."],
    )
    result = service.process(request)

    assert result.intent_type == "update_request"
    assert result.update_type == "mobile_number"
    assert any(entity.entity_type == "mobile_number" and "9876543210" in entity.value for entity in result.entities)
