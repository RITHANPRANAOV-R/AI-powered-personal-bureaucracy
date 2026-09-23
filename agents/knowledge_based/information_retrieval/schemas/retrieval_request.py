"""
Retrieval Request and Requirement contracts from Intent Understanding Agent.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


class RetrievalRequirement(BaseModel):
    """
    Represents a specific required aspect of information (e.g. eligibility, fees).
    """
    model_config = ConfigDict(extra="ignore")

    requirement_id: str = Field(description="Identifier for requirement item")
    category: str = Field(description="Category of requirement e.g. 'eligibility', 'fees'")
    description: str = Field(description="Detailed query/question to resolve")
    mandatory: bool = Field(default=True, description="Whether requirement is mandatory")


class UserDocumentInput(BaseModel):
    """
    Represents user-uploaded document inputs passed to IR Agent.
    """
    model_config = ConfigDict(extra="ignore")

    document_id: str = Field(description="Unique ID of user document")
    document_type: str = Field(description="Stated type of document e.g. 'voter_id', 'passport'")
    file_path: Optional[str] = Field(default=None, description="Local or temp path to file")
    extracted_fields: Dict[str, Any] = Field(default_factory=dict, description="Fields extracted via OCR/parser")


class RetrievalRequest(BaseModel):
    """
    Structured input request sent from Intent Understanding Agent to Information Retrieval Agent.
    """
    model_config = ConfigDict(extra="ignore")

    request_id: str = Field(description="Unique request session identifier")
    goal: str = Field(description="User's overarching goal e.g. 'Update Aadhaar address'")
    service: str = Field(description="Target government service e.g. 'Aadhaar Address Update'")
    domain: str = Field(default="aadhaar", description="Government domain category e.g. 'aadhaar'")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entity key-values")
    information_needed: List[str] = Field(
        default_factory=list,
        description="List of information aspect keys e.g. ['eligibility', 'fees', 'documents']"
    )
    requirements: List[RetrievalRequirement] = Field(
        default_factory=list,
        description="Detailed retrieval requirements"
    )
    user_documents: List[UserDocumentInput] = Field(
        default_factory=list,
        description="User-uploaded document references"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of request creation"
    )
