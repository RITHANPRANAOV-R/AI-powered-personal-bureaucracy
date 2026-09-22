from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

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


class IntentRequest(BaseModel):
    session_id: str
    user_message: str
    conversation_history: Optional[list[str]] = None
    current_intent: Optional[Any] = None


class IntentResult(BaseModel):
    session_id: str
    intent_type: str
    update_type: Optional[str] = None
    summary: str
    entities: list[ExtractedEntity] = Field(default_factory=list)
    urgency: str = "normal"
    missing_information: list[MissingInformation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class IntentEvent(BaseModel):
    event_id: str
    session_id: str
    event_type: str
    intent: str
    timestamp: datetime
    source_agent: str = "intent_understanding"
