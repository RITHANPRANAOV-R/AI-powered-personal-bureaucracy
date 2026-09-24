try:
    from .agent import ComplianceValidationAgent
    from .schema import ComplianceValidationInput
except ImportError:  # pragma: no cover - direct script execution fallback
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from agents.knowledge_based.compliance_validation.agent import ComplianceValidationAgent
    from agents.knowledge_based.compliance_validation.schema import ComplianceValidationInput


def build_examples():
    agent = ComplianceValidationAgent()

    pass_data = ComplianceValidationInput(
        user_information={
            "name": "Rahul",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "passport": True,
            "address_proof": True,
        },
        requirements={
            "source": "Official service requirements",
            "required_information": [
                "name",
                "date_of_birth",
                "address",
            ],
            "required_documents": [
                "passport",
                "address_proof",
            ],
            "required_form_fields": [
                "name",
                "date_of_birth",
                "address",
            ],
        },
        form_data={
            "name": "Rahul",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
    )

    warning_data = ComplianceValidationInput(
        user_information={
            "name": "Rahul",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "passport": True,
            "address_proof": False,
        },
        requirements={
            "source": "Official service requirements",
            "required_information": [
                "name",
                "date_of_birth",
                "address",
            ],
            "required_documents": [
                "passport",
                "address_proof",
            ],
            "required_form_fields": [
                "name",
                "date_of_birth",
                "address",
            ],
        },
        form_data={
            "name": "Rahul",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
    )

    blocked_data = ComplianceValidationInput(
        user_information={
            "name": "Rahul",
            "date_of_birth": "2003-05-10",
            "address": "12 ABC Street",
        },
        documents={
            "passport": True,
            "address_proof": True,
        },
        requirements={
            "source": "Official service requirements",
            "required_information": [
                "name",
                "date_of_birth",
                "address",
            ],
            "required_documents": [
                "passport",
                "address_proof",
            ],
            "required_form_fields": [
                "name",
                "date_of_birth",
                "address",
            ],
            "sensitive_action": True,
            "authorization_confirmed": False,
        },
        form_data={
            "name": "Rahul",
            "date_of_birth": "2004-05-10",
            "address": "12 ABC Street",
        },
    )

    return {
        "PASS": agent.run(pass_data),
        "WARNING": agent.run(warning_data),
        "BLOCKED": agent.run(blocked_data),
    }


if __name__ == "__main__":
    for label, result in build_examples().items():
        print(f"\nTEST {label}")
        print(result.model_dump())