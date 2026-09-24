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
    ] = "general_assistance"
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
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = Field(default=1, ge=1)
    change_history: list[ChangeDelta] = Field(default_factory=list)


class MonitoringApplicationInput(BaseModel):
    application_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    service_type: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    previous_status: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    required_action: Optional[str] = None
    pending_action: Optional[str] = None
    deadline: Optional[datetime] = None
    source: str = Field(default="system", min_length=1)
    event_type: str = Field(default="status_update", min_length=1)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class MonitoringEvent(BaseModel):
    application_id: str = Field(min_length=1)
    service_id: Optional[str] = None
    service_type: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    previous_status: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    required_action: Optional[str] = None
    pending_action: Optional[str] = None
    deadline: Optional[datetime] = None
    source: str = Field(default="system", min_length=1)
    event_type: str = Field(default="status_update", min_length=1)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ChangeDelta",
    "MonitoringApplicationInput",
    "MonitoringEvent",
    "SessionState",
]
