"""
Vector Retriever for Information Retrieval Agent.
Queries ChromaDB knowledge base for RetrievalRequests and formats candidate evidence.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType
from agents.knowledge_based.information_retrieval.schemas.evidence import Evidence
from agents.knowledge_based.information_retrieval.schemas.retrieval_request import (
    RetrievalRequest,
)
from agents.knowledge_based.information_retrieval.schemas.retrieval_result import (
    RetrievalResult,
    RetrievalStatus,
    WarningItem,
)
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry
from agents.knowledge_based.information_retrieval.retrieval.vector_store import ChromaVectorStore
from agents.knowledge_based.information_retrieval.retrieval.query_builder import QueryBuilder, ConstructedQuery

logger = logging.getLogger(__name__)


class VectorRetriever:
    """
    Executes semantic vector searches against ChromaDB knowledge store for RetrievalRequests.
    """

    def __init__(
        self,
        vector_store: Optional[ChromaVectorStore] = None,
        source_registry: Optional[SourceRegistry] = None,
        query_builder: Optional[QueryBuilder] = None,
        top_k: int = 5,
    ):
        self.vector_store = vector_store or ChromaVectorStore()
        self.source_registry = source_registry or SourceRegistry(include_defaults=True)
        self.query_builder = query_builder or QueryBuilder()
        self.default_top_k = top_k

    def retrieve_for_request(
        self,
        request: RetrievalRequest,
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        """
        Processes a RetrievalRequest, constructs queries, executes vector search, and returns candidate Evidence.
        """
        effective_top_k = top_k if (top_k is not None and top_k > 0) else self.default_top_k

        if not request or not request.request_id:
            return RetrievalResult(
                result_id="res_invalid",
                request_id="unknown",
                service="unknown",
                domain="unknown",
                retrieval_status=RetrievalStatus.FAILED,
                warnings=[
                    WarningItem(
                        warning_id="warn_invalid_request",
                        code="INVALID_REQUEST",
                        message="RetrievalRequest is null or missing request_id",
                    )
                ],
            )

        # Build queries for requirements
        constructed_queries = self.query_builder.build_queries(request)
        if not constructed_queries:
            return RetrievalResult(
                result_id=f"res_{request.request_id}",
                request_id=request.request_id,
                service=request.service or "general",
                domain=request.domain or "aadhaar",
                retrieval_status=RetrievalStatus.NO_EVIDENCE_FOUND,
                warnings=[
                    WarningItem(
                        warning_id="warn_no_queries",
                        code="NO_QUERIES_GENERATED",
                        message="No valid search queries could be constructed from request",
                    )
                ],
            )

        # Dictionary for deduplicating evidence by chunk_id while preserving requirement associations
        evidence_by_chunk_id: Dict[str, Evidence] = {}
        sources_by_id: Dict[str, Source] = {}
        requirement_summaries: List[Dict[str, Any]] = []

        for q in constructed_queries:
            req_summary = {
                "requirement_id": q.requirement_id,
                "category": q.category,
                "query": q.normalized_query,
            }
            requirement_summaries.append(req_summary)

            try:
                hits = self.vector_store.query_similar(q.normalized_query, top_k=effective_top_k)
            except Exception as e:
                logger.error(f"Vector search failed for query '{q.normalized_query}': {e}")
                hits = []

            for hit in hits:
                chunk_id = hit["chunk_id"]
                text = hit["text"]
                metadata = hit["metadata"] or {}
                distance = hit.get("distance")

                source_id = metadata.get("source_id", "src_unknown")
                authority = metadata.get("authority", "UIDAI")
                doc_title = metadata.get("document_title", "Official Government Document")
                doc_url = metadata.get("document_url", "")
                page_num = metadata.get("page_number")
                retrieved_at = metadata.get("retrieved_at", datetime.now(timezone.utc).isoformat())

                # Resolve or construct Source
                if source_id in sources_by_id:
                    source_obj = sources_by_id[source_id]
                else:
                    reg_source = self.source_registry.get_source(source_id)
                    if reg_source:
                        source_obj = reg_source
                    else:
                        source_obj = Source(
                            source_id=source_id,
                            authority=authority,
                            domain=request.domain or "aadhaar",
                            url=doc_url,
                            document_title=doc_title,
                            source_type=SourceType.OFFICIAL_PDF if doc_url.endswith(".pdf") else SourceType.LIVE_WEBPAGE,
                        )
                    sources_by_id[source_id] = source_obj

                # Distance to relevance score mapping (lower distance = higher relevance)
                if distance is not None:
                    relevance = max(0.0, min(1.0, 1.0 - float(distance)))
                else:
                    relevance = 1.0

                if chunk_id in evidence_by_chunk_id:
                    # Update existing candidate evidence with additional requirement association
                    existing = evidence_by_chunk_id[chunk_id]
                    req_list = existing.metadata.get("associated_requirements", [])
                    if q.requirement_id not in req_list:
                        req_list.append(q.requirement_id)
                    existing.metadata["associated_requirements"] = req_list
                else:
                    # Create new Evidence candidate
                    evidence_item = Evidence(
                        evidence_id=chunk_id,
                        claim=f"Candidate evidence for {q.category} ({q.normalized_query})",
                        passage=text,
                        source=source_obj,
                        retrieved_at=retrieved_at,
                        page_number=page_num,
                        confidence=1.0,
                        relevance_score=relevance,
                        metadata={
                            "chunk_id": chunk_id,
                            "query_used": q.normalized_query,
                            "associated_requirements": [q.requirement_id],
                            "category": q.category,
                            "distance": distance,
                        },
                    )
                    evidence_by_chunk_id[chunk_id] = evidence_item

        all_evidence = list(evidence_by_chunk_id.values())
        status = RetrievalStatus.SUCCESS if all_evidence else RetrievalStatus.NO_EVIDENCE_FOUND

        warnings = []
        if status == RetrievalStatus.NO_EVIDENCE_FOUND:
            warnings.append(
                WarningItem(
                    warning_id="warn_no_hits",
                    code="NO_EVIDENCE_FOUND",
                    message="No relevant evidence chunks matched the queries in ChromaDB",
                )
            )

        return RetrievalResult(
            result_id=f"res_{request.request_id}",
            request_id=request.request_id,
            service=request.service,
            domain=request.domain,
            retrieval_status=status,
            requirements=requirement_summaries,
            evidence=all_evidence,
            sources=list(sources_by_id.values()),
            warnings=warnings,
            metadata={
                "top_k": effective_top_k,
                "total_queries_executed": len(constructed_queries),
                "total_candidate_chunks_retrieved": len(all_evidence),
            },
        )
