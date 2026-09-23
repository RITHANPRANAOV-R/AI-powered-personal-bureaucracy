from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from agents.orchestration.intent_understanding.schemas import ExtractedEntity, MissingInformation


class ChangeDelta(BaseModel):
    field_name: str
    previous_value: Any = None
    new_value: Any = None
    change_type: str
    reason: str = ""


class SessionState(BaseModel):
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
    missing_information: list[MissingInformation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = Field(default=1, ge=1)
    change_history: list[ChangeDelta] = Field(default_factory=list)
