"""
Schemas Package for Information Retrieval Agent contracts.
"""
from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType
from agents.knowledge_based.information_retrieval.schemas.evidence import Evidence, GroundingStatus
from agents.knowledge_based.information_retrieval.schemas.retrieval_request import (
    RetrievalRequest,
    RetrievalRequirement,
    UserDocumentInput,
)
from agents.knowledge_based.information_retrieval.schemas.retrieval_result import (
    RetrievalResult,
    RetrievalStatus,
    ConflictItem,
    WarningItem,
)
from agents.knowledge_based.information_retrieval.schemas.user_document import (
    UserDocument,
    ExtractedField,
    DocumentType,
    ExtractionMethod,
    OCRStatus,
)
from agents.knowledge_based.information_retrieval.schemas.linking import (
    LinkStatus,
    RequirementDocumentLink,
    LinkingResult,
)

__all__ = [
    "Source",
    "SourceType",
    "Evidence",
    "GroundingStatus",
    "RetrievalRequest",
    "RetrievalRequirement",
    "UserDocumentInput",
    "RetrievalResult",
    "RetrievalStatus",
    "ConflictItem",
    "WarningItem",
    "UserDocument",
    "ExtractedField",
    "DocumentType",
    "ExtractionMethod",
    "OCRStatus",
    "LinkStatus",
    "RequirementDocumentLink",
    "LinkingResult",
]
