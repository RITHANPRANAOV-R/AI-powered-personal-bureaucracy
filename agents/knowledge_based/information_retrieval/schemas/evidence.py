"""
Evidence schema representing retrieved passages, grounding verification, and ranking scores.
"""
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
from agents.knowledge_based.information_retrieval.schemas.source import Source


class GroundingStatus(str, Enum):
    """Grounding verification status of evidence items."""
    VERIFIED_GROUNDED = "verified_grounded"
    UNVERIFIED = "unverified"
    INVALID = "invalid"


class Evidence(BaseModel):
    """
    Represents a specific passage or data point extracted from an authoritative source.
    """
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    evidence_id: str = Field(description="Unique identifier for the evidence entry")
    claim: str = Field(description="The claim or topic supported by this evidence")
    passage: str = Field(description="Exact retrieved text or data content")
    source: Source = Field(description="Associated source metadata")
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp when evidence was retrieved"
    )
    page_number: Optional[int] = Field(default=None, description="Page number if from document")
    section: Optional[str] = Field(default=None, description="Section heading if available")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Search relevance score")
    ranking_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Deterministic overall ranking score")
    grounding_status: GroundingStatus = Field(
        default=GroundingStatus.UNVERIFIED,
        description="Grounding verification classification"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")
