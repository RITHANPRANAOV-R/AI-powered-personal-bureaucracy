"""
Source metadata and authority schemas for Information Retrieval Agent.
"""
from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


class SourceType(str, Enum):
    """Classification of document / data source types."""
    LIVE_WEBPAGE = "live_webpage"
    GOVERNMENT_API = "government_api"
    OFFICIAL_PDF = "official_pdf"
    REGULATION = "regulation"
    OFFICIAL_FORM = "official_form"
    OFFICIAL_FAQ = "official_faq"
    USER_DOCUMENT = "user_document"
    OTHER = "other"


class Source(BaseModel):
    """
    Represents metadata for an authoritative source.
    """
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    source_id: str = Field(description="Unique identifier for the source")
    authority: str = Field(description="Governing authority, e.g. UIDAI")
    domain: str = Field(description="Domain category, e.g. aadhaar")
    url: Optional[str] = Field(default=None, description="Official URL of the source")
    document_title: Optional[str] = Field(default=None, description="Title of document or web page")
    source_type: SourceType = Field(default=SourceType.LIVE_WEBPAGE, description="Type of source")
    trust_level: float = Field(default=1.0, ge=0.0, le=1.0, description="Trust score (1.0 = official authority)")
    last_checked: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp when source was last checked"
    )
    freshness_policy: Optional[str] = Field(default="live", description="Freshness expectation policy")
    active: bool = Field(default=True, description="Whether the source is currently active")
