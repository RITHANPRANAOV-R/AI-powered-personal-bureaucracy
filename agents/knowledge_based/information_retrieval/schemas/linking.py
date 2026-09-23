"""
Requirement to User Document Linking Schema.
Defines neutral candidate matching, missing document gaps, field coverage, and provenance contracts.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


class LinkStatus(str, Enum):
    """Execution status of Requirement to Document candidate matching."""
    CANDIDATE_MATCH = "candidate_match"
    PARTIAL_MATCH = "partial_match"
    MISSING_DOCUMENT = "missing_document"
    MISSING_FIELD = "missing_field"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class RequirementDocumentLink(BaseModel):
    """
    Represents the evidence relationship between an official government requirement and candidate user document(s).
    """
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    link_id: str = Field(description="Unique ID for requirement-document link")
    requirement_id: str = Field(description="Associated requirement ID from RetrievalResult")
    requirement_category: str = Field(description="Requirement category e.g. 'address', 'identity'")
    requirement_description: str = Field(description="Full text description of requirement")
    status: LinkStatus = Field(default=LinkStatus.UNKNOWN, description="Candidate relationship status")

    matched_document_id: Optional[str] = Field(default=None, description="Candidate matching user document ID")
    matched_document_type: Optional[str] = Field(default=None, description="Document type e.g. 'aadhaar'")
    matched_fields: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted fields supporting match")
    missing_fields: List[str] = Field(default_factory=list, description="Expected fields missing from candidate document")
    matching_reasons: List[str] = Field(default_factory=list, description="Inspectable explanation for candidate link")
    official_evidence_ids: List[str] = Field(default_factory=list, description="Associated official evidence IDs")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Link candidate confidence score")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Context metadata and page provenance")


class LinkingResult(BaseModel):
    """
    Structured outcome of requirement ↔ user document linking pipeline.
    """
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    linking_id: str = Field(description="Unique ID for linking session")
    request_id: str = Field(description="Corresponding retrieval request ID")
    links: List[RequirementDocumentLink] = Field(default_factory=list, description="All requirement candidate links")
    uncovered_requirements: List[str] = Field(default_factory=list, description="Requirement IDs lacking candidate documents")
    conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="Detected field conflicts across user documents")
    warnings: List[str] = Field(default_factory=list, description="Processing warnings or uncertainties")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of linking execution"
    )
