from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, TypeAdapter


class ExecutionResult(BaseModel):
    """
    Standardized input contract expected by Response Generation Agent from upstream execution agents.
    Designed to support any government document workflow (Aadhaar, Passport, Community Cert, etc.)
    """
    service_name: str = Field(
        description="Name of the government service, e.g., 'Aadhaar Address Update', 'Passport Renewal', 'Community Certificate Application'"
    )
    document_type: str = Field(
        description="Type of document, e.g., 'Aadhaar', 'Passport', 'Community Certificate'"
    )
    overall_status: str = Field(
        description="Current progress state: 'COMPLETED', 'IN_PROGRESS', 'ACTION_REQUIRED', 'BLOCKED', 'FAILED'"
    )
    completed_steps: List[str] = Field(
        default_factory=list,
        description="List of workflow actions successfully completed so far"
    )
    pending_steps: List[str] = Field(
        default_factory=list,
        description="List of future workflow steps remaining"
    )
    action_required: Optional[str] = Field(
        default=None,
        description="Immediate action required by the citizen, if any"
    )
    important_details: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Key process details such as fees, deadlines, reference numbers, appointment details"
    )
    missing_information: Optional[List[str]] = Field(
        default_factory=list,
        description="List of documents or details missing from the citizen"
    )
    official_references: Optional[List[str]] = Field(
        default_factory=list,
        description="Official links, guidelines, or portal references"
    )
    user_language: Optional[str] = Field(
        default="English",
        description="Preferred response language (e.g., 'English', 'Hindi', 'Tamil')"
    )


class CitizenResponse(BaseModel):
    """
    Structured output contract produced by Response Generation Agent for the Interface Layer / UI Dashboard.
    """
    headline: str = Field(
        description="Short, clear title summarizing the current status for the citizen"
    )
    summary: str = Field(
        description="1-2 sentence plain language overview of current progress"
    )
    completed_actions: List[str] = Field(
        default_factory=list,
        description="Clean list of completed workflow steps"
    )
    pending_actions: List[str] = Field(
        default_factory=list,
        description="Clean list of pending workflow steps"
    )
    citizen_next_step: Optional[str] = Field(
        default=None,
        description="Single actionable step the citizen must perform next"
    )
    key_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Important deadlines, fees, reference numbers, appointment dates"
    )
    missing_items: List[str] = Field(
        default_factory=list,
        description="Missing items or documents that require attention"
    )
    official_links: List[str] = Field(
        default_factory=list,
        description="Portal links, reference numbers, or guidelines"
    )
    formatted_markdown: str = Field(
        description="Complete formatted markdown response ready to be rendered in the Chat UI"
    )


def get_clean_output_schema(model_cls):
    """
    Generates a clean JSON schema dict compatible with Gemini Developer API mode
    by stripping 'additionalProperties' keys which cause validation errors in developer API mode.
    """
    schema_dict = TypeAdapter(model_cls).json_schema()

    def _clean(d):
        if isinstance(d, dict):
            d.pop('additionalProperties', None)
            for v in d.values():
                _clean(v)
        elif isinstance(d, list):
            for item in d:
                _clean(item)

    _clean(schema_dict)
    return schema_dict
