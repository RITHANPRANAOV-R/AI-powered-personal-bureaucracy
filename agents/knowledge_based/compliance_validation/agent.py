from google.adk.agents import Agent

from .schema import ComplianceValidationInput, ComplianceValidationResult
from .validator import ComplianceValidator


validator = ComplianceValidator()


class ComplianceValidationAgent:
    """Agent wrapper for deterministic compliance and validation checks."""

    def __init__(self):
        self.validator = validator

    def run(self, data: ComplianceValidationInput) -> ComplianceValidationResult:
        return self.validator.validate(data)


def validate_compliance(
    user_information: dict,
    documents: dict,
    requirements: dict,
    form_data: dict,
    document_type: str = "OTHER",
    service_type: str = "general_service",
    confidence: dict | None = None,
) -> dict:
    """Validate a document or application using official requirements as the source of truth."""
    data = ComplianceValidationInput(
        document_type=document_type,
        service_type=service_type,
        user_information=user_information,
        documents=documents,
        requirements=requirements,
        form_data=form_data,
        confidence=confidence or {},
    )
    result = validator.validate(data)
    return result.model_dump()


root_agent = Agent(
    name="compliance_validation_agent",
    model="gemini-3.8-flash",
    instruction="""
You are the Compliance and Validation Agent for an AI-Powered Personal Bureaucracy system.

Your job is to act as the final quality gate before an important submission or action.

Responsibilities:
- Validate user information against official requirements.
- Validate submitted documents for completeness, usability, expiry, and required content.
- Cross-check document details with user and form data.
- Detect missing or inconsistent information.
- Check security, privacy, and authorization requirements.
- Return one of three statuses: PASS, WARNING, or BLOCKED.
- Use deterministic validation logic as the primary source of truth.
- Do not invent missing government rules or assume information is correct without evidence.
- Treat the document type, service type, and requirement set as configurable and extensible.

Before allowing workflow continuation:
- confirm each required document and field is valid,
- validate identity and form consistency,
- flag security or authorization issues,
- and return structured evidence using:

Source → Requirement → Evidence → Result → Next Action

Always use the validate_compliance tool when a validation decision is required.
""",
    tools=[validate_compliance],
)