"""
Structured Retrieval Result schema returned to Workflow Planning Agent.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
from agents.knowledge_based.information_retrieval.schemas.source import Source
from agents.knowledge_based.information_retrieval.schemas.evidence import Evidence


class RetrievalStatus(str, Enum):
    """Execution status of Information Retrieval pipeline."""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    NO_EVIDENCE_FOUND = "no_evidence_found"
    SOURCE_UNAVAILABLE = "source_unavailable"
    FAILED = "failed"


class ConflictItem(BaseModel):
    """
    Represents detected conflicts between multiple authoritative sources.
    """
    model_config = ConfigDict(extra="ignore")

    conflict_id: str = Field(description="Unique ID for conflict record")
    topic: str = Field(description="Subject matter of conflict e.g. 'fee amount'")
    description: str = Field(description="Explanation of conflicting claims")
    sources: List[Source] = Field(default_factory=list, description="Sources involved in conflict")
    evidence_list: List[Evidence] = Field(default_factory=list, description="Conflicting evidence items")


class WarningItem(BaseModel):
    """
    Represents non-fatal warnings or uncertainties during retrieval.
    """
    model_config = ConfigDict(extra="ignore")

    warning_id: str = Field(description="Unique ID for warning")
    code: str = Field(description="Warning category code")
    message: str = Field(description="Human-readable warning details")
    source_id: Optional[str] = Field(default=None, description="Associated source ID if applicable")


class RetrievalResult(BaseModel):
    """
    Final structured, source-grounded result output provided to Workflow Planning Agent.
    """
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    result_id: str = Field(description="Unique identifier for retrieval result")
    request_id: str = Field(description="Corresponding input request ID")
    service: str = Field(description="Target government service name")
    domain: str = Field(description="Government domain e.g. 'aadhaar'")
    retrieval_status: RetrievalStatus = Field(default=RetrievalStatus.SUCCESS, description="Status of retrieval")
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp when retrieval completed"
    )

    requirements: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted requirement summaries")
    procedure: List[Dict[str, Any]] = Field(default_factory=list, description="Step-by-step procedural steps")
    forms: List[Dict[str, Any]] = Field(default_factory=list, description="Associated official forms metadata")
    appointment: Dict[str, Any] = Field(default_factory=dict, description="Appointment & center visit requirements")
    fees: Dict[str, Any] = Field(default_factory=dict, description="Current applicable fees structure")
    restrictions: List[str] = Field(default_factory=list, description="Service update restrictions / limitations")
    user_documents: List[Dict[str, Any]] = Field(default_factory=list, description="Processed user document evidence")

    evidence: List[Evidence] = Field(default_factory=list, description="All grounded evidence items")
    sources: List[Source] = Field(default_factory=list, description="All referenced authoritative sources")
    conflicts: List[ConflictItem] = Field(default_factory=list, description="Detected source conflicts")
    warnings: List[WarningItem] = Field(default_factory=list, description="Retrieval warnings or missing info notes")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or execution stats")
