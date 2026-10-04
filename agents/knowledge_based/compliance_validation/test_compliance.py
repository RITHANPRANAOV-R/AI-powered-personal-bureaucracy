from .agent import ComplianceValidationAgent
from .schema import ComplianceValidationInput


def build_requirements(service_name="service_registration"):
    return {
        "source": "Official requirement supplied by Information Retrieval Agent",
        "service_type": service_name,
        "required_information": ["name", "date_of_birth", "address"],
        "required_documents": ["passport", "address_proof"],
        "required_form_fields": ["name", "date_of_birth", "address"],
    }


def test_valid_document_passes():
    agent = ComplianceValidationAgent()
    data = ComplianceValidationInput(
        document_type="PASSPORT",
        service_type="service_registration",
        user_information={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "passport": {"readable": True, "valid": True, "expiry_valid": True, "name": "Rahul Kumar"},
            "address_proof": {"readable": True, "valid": True, "expiry_valid": True, "address": "12 ABC Street"},
        },
        requirements=build_requirements(),
        form_data={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
    )

    result = agent.run(data)

    assert result.status.value == "PASS"
    assert result.missing_information == []
    assert result.missing_documents == []
    assert result.invalid_documents == []


def test_missing_document_warns():
    agent = ComplianceValidationAgent()
    data = ComplianceValidationInput(
        document_type="PASSPORT",
        service_type="service_registration",
        user_information={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "passport": {"readable": True, "valid": True, "expiry_valid": True, "name": "Rahul Kumar"},
            "address_proof": False,
        },
        requirements=build_requirements(),
        form_data={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
    )

    result = agent.run(data)

    assert result.status.value == "WARNING"
    assert "address_proof" in result.missing_documents


def test_missing_required_field_warns():
    agent = ComplianceValidationAgent()
    data = ComplianceValidationInput(
        document_type="AADHAAR",
        service_type="identity_verification",
        user_information={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
        },
        documents={
            "aadhaar": {"readable": True, "valid": True, "expiry_valid": True, "name": "Rahul Kumar"},
        },
        requirements={
            "source": "Official requirement supplied by Information Retrieval Agent",
            "service_type": "identity_verification",
            "required_information": ["name", "date_of_birth", "address"],
            "required_documents": ["aadhaar"],
            "required_form_fields": ["name", "date_of_birth", "address"],
        },
        form_data={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "",
        },
    )

    result = agent.run(data)

    assert result.status.value == "WARNING"
    assert any("address" in item for item in result.missing_information)
    assert any("address" in item for item in result.form_errors)


def test_document_and_form_mismatch_blocks():
    agent = ComplianceValidationAgent()
    data = ComplianceValidationInput(
        document_type="PASSPORT",
        service_type="service_registration",
        user_information={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "passport": {"readable": True, "valid": True, "expiry_valid": True, "name": "Rahul Kumar"},
        },
        requirements={
            "source": "Official requirement supplied by Information Retrieval Agent",
            "service_type": "service_registration",
            "required_information": ["name", "date_of_birth", "address"],
            "required_documents": ["passport"],
            "required_form_fields": ["name", "date_of_birth", "address"],
        },
        form_data={
            "name": "Rahul Kumar",
            "date_of_birth": "2004-05-10",
            "address": "12 ABC Street",
        },
    )

    result = agent.run(data)

    assert result.status.value == "BLOCKED"
    assert any("date_of_birth" in item for item in result.inconsistencies)


def test_cross_document_mismatch_blocks():
    agent = ComplianceValidationAgent()
    data = ComplianceValidationInput(
        document_type="AADHAAR",
        service_type="identity_verification",
        user_information={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "aadhaar": {"readable": True, "valid": True, "expiry_valid": True, "name": "Rahul Kumar"},
            "passport": {"readable": True, "valid": True, "expiry_valid": True, "name": "R. Kumar"},
        },
        requirements={
            "source": "Official requirement supplied by Information Retrieval Agent",
            "service_type": "identity_verification",
            "required_information": ["name", "date_of_birth", "address"],
            "required_documents": ["aadhaar", "passport"],
            "required_form_fields": ["name", "date_of_birth", "address"],
        },
        form_data={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
    )

    result = agent.run(data)

    assert result.status.value == "BLOCKED"
    assert any("name" in item for item in result.inconsistencies)


def test_security_and_authorization_problem_blocks():
    agent = ComplianceValidationAgent()
    data = ComplianceValidationInput(
        document_type="AADHAAR",
        service_type="sensitive_submission",
        user_information={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "aadhaar": {"readable": True, "valid": True, "expiry_valid": True, "name": "Rahul Kumar"},
        },
        requirements={
            "source": "Official requirement supplied by Information Retrieval Agent",
            "service_type": "sensitive_submission",
            "required_information": ["name", "date_of_birth", "address"],
            "required_documents": ["aadhaar"],
            "required_form_fields": ["name", "date_of_birth", "address"],
            "sensitive_action": True,
            "authorization_confirmed": False,
        },
        form_data={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
    )

    result = agent.run(data)

    assert result.status.value == "BLOCKED"
    assert result.security_issues


def test_high_impact_action_blocks_unverified_information():
    agent = ComplianceValidationAgent()
    data = ComplianceValidationInput(
        document_type="PASSPORT",
        service_type="sensitive_submission",
        user_information={"name": "Rahul Kumar"},
        documents={
            "passport": {
                "readable": True,
                "valid": True,
                "expiry_valid": True,
                "name": "Rahul Kumar",
            },
        },
        requirements={
            "source": "Official requirement supplied by Information Retrieval Agent",
            "required_documents": ["passport"],
            "sensitive_action": True,
            "authorization_confirmed": True,
        },
        confidence={"name": "VERIFIED", "date_of_birth": "UNKNOWN"},
    )

    result = agent.run(data)

    assert result.status.value == "BLOCKED"
    assert any("inferred or unknown" in issue for issue in result.security_issues)


def test_aadhaar_example_supports_generic_model():
    agent = ComplianceValidationAgent()
    data = ComplianceValidationInput(
        document_type="AADHAAR",
        service_type="benefit_application",
        user_information={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "aadhaar": {"readable": True, "valid": True, "expiry_valid": True, "name": "Rahul Kumar", "address": "12 ABC Street"},
        },
        requirements={
            "source": "Official requirement supplied by Information Retrieval Agent",
            "service_type": "benefit_application",
            "required_information": ["name", "date_of_birth", "address"],
            "required_documents": ["aadhaar"],
            "required_form_fields": ["name", "date_of_birth", "address"],
        },
        form_data={
            "name": "Rahul Kumar",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
    )

    result = agent.run(data)

    assert result.status.value == "PASS"
    assert result.document_type == "AADHAAR"