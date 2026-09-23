"""
Query Builder and Normalizer for Information Retrieval Agent.
Constructs semantic search queries from RetrievalRequest objects.
"""
import re
import logging
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

from agents.knowledge_based.information_retrieval.schemas.retrieval_request import (
    RetrievalRequest,
    RetrievalRequirement,
)

logger = logging.getLogger(__name__)


class ConstructedQuery(BaseModel):
    """
    Represents a normalized semantic search query tied to a specific requirement.
    """
    model_config = ConfigDict(extra="ignore")

    requirement_id: str = Field(description="Associated requirement ID")
    category: str = Field(description="Requirement category e.g. 'fees', 'documents'")
    raw_query: str = Field(description="Raw constructed query string")
    normalized_query: str = Field(description="Cleaned, normalized query string for vector search")


class QueryNormalizer:
    """
    Lightweight deterministic text normalizer for retrieval queries.
    Preserves government terms, acronyms (UIDAI, SSUP, PVC), numbers, and entities while removing punctuation noise.
    """

    WHITESPACE_REGEX = re.compile(r"\s+")
    NOISE_CHARS_REGEX = re.compile(r"[^\w\s\-]")

    def normalize(self, text: str) -> str:
        """Normalizes whitespace and removes punctuation noise."""
        if not text:
            return ""

        # Clean punctuation characters while preserving alphanumeric, hyphens, and whitespace
        cleaned = self.NOISE_CHARS_REGEX.sub(" ", text)
        # Collapse whitespace
        normalized = self.WHITESPACE_REGEX.sub(" ", cleaned).strip()

        return normalized


class QueryBuilder:
    """
    Constructs focused semantic retrieval queries from RetrievalRequest specifications.
    """

    def __init__(self, normalizer: Optional[QueryNormalizer] = None):
        self.normalizer = normalizer or QueryNormalizer()

    def build_queries(self, request: RetrievalRequest) -> List[ConstructedQuery]:
        """
        Builds a list of search queries from a RetrievalRequest.
        """
        if not request:
            return []

        domain = request.domain or "aadhaar"
        service = request.service or ""

        # Extract entity terms if present
        entity_terms = []
        if request.entities:
            for k, v in request.entities.items():
                if isinstance(v, str) and v.strip():
                    entity_terms.append(v.strip())
        entity_str = " ".join(entity_terms)

        constructed_queries: List[ConstructedQuery] = []

        # 1. Process explicit requirements list
        if request.requirements:
            for req in request.requirements:
                query_str = self._build_single_query(domain, service, entity_str, req.category, req.description)
                norm_str = self.normalizer.normalize(query_str)
                if norm_str:
                    constructed_queries.append(
                        ConstructedQuery(
                            requirement_id=req.requirement_id,
                            category=req.category,
                            raw_query=query_str,
                            normalized_query=norm_str,
                        )
                    )

        # 2. Fallback to information_needed strings if no explicit requirements provided
        elif request.information_needed:
            for idx, aspect in enumerate(request.information_needed):
                req_id = f"info_req_{idx+1}"
                query_str = self._build_single_query(domain, service, entity_str, aspect, aspect)
                norm_str = self.normalizer.normalize(query_str)
                if norm_str:
                    constructed_queries.append(
                        ConstructedQuery(
                            requirement_id=req_id,
                            category=aspect,
                            raw_query=query_str,
                            normalized_query=norm_str,
                        )
                    )

        # 3. Ultimate fallback: query using goal or service if no requirements specified
        if not constructed_queries and (request.goal or request.service):
            fallback_text = request.goal or request.service
            norm_str = self.normalizer.normalize(f"{domain} {fallback_text}")
            if norm_str:
                constructed_queries.append(
                    ConstructedQuery(
                        requirement_id="req_fallback_general",
                        category="general",
                        raw_query=fallback_text,
                        normalized_query=norm_str,
                    )
                )

        return constructed_queries

    def _build_single_query(
        self, domain: str, service: str, entity_str: str, category: str, description: str
    ) -> str:
        """Formats query text combining domain, service, entities, and requirement."""
        parts = [domain]
        if service:
            parts.append(service)
        if entity_str:
            parts.append(entity_str)
        if category and category.lower() not in service.lower():
            parts.append(category)
        if description and description.lower() != category.lower():
            parts.append(description)

        return " ".join(parts)
