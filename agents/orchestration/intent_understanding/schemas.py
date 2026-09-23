from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ExtractedEntity(BaseModel):
    entity_type: str
    value: str
    normalized_value: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_text: Optional[str] = None


class MissingInformation(BaseModel):
    field_name: str
    reason: str
    required: bool = True
    severity: str = "medium"


class UserRequestInput(BaseModel):
    session_id: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    conversation_history: Optional[list[str]] = None
    current_session_state: Optional[dict[str, Any]] = None
    domain: str = Field(default="aadhaar", min_length=1)


class IntentClassificationResult(BaseModel):
    session_id: str = Field(min_length=1)
    intent_type: Literal[
        "status_inquiry",
        "update_request",
        "correction_request",
        "document_request",
        "complaint",
        "enrollment",
        "general_assistance",
    ]
    update_type: Optional[Literal[
        "address",
        "mobile_number",
        "email",
        "name",
        "date_of_birth",
        "gender",
        "biometric",
        "unknown",
    ]] = None
    summary: str = Field(min_length=1)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    urgency: Literal["low", "normal", "high"] = "normal"
    missing_information: list[MissingInformation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
