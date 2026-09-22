from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class IntentState(BaseModel):
    session_id: str
    intent_type: str
    update_type: Optional[str] = None
    summary: str
    entities: list[Any] = Field(default_factory=list)
    urgency: str = "normal"
    missing_information: list[Any] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    last_updated: datetime
    version: int = 1
    change_history: list[str] = Field(default_factory=list)


class ChangeDelta(BaseModel):
    field_name: str
    previous_value: Any = None
    new_value: Any = None
    change_type: str
    reason: str = ""


class UpdateRequest(BaseModel):
    session_id: str
    previous_state: IntentState
    new_intent: Any


class UpdateResult(BaseModel):
    session_id: str
    changes: list[ChangeDelta] = Field(default_factory=list)
    updated_state: IntentState
    events: list[Any] = Field(default_factory=list)


class MonitoringEvent(BaseModel):
    event_id: str
    session_id: str
    event_type: str
    timestamp: datetime
    intent_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
