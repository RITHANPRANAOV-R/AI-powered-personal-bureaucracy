"""
Hybrid Retriever combining ChromaDB persistent vector search and live government HTTP retrieval.
"""
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
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
from agents.knowledge_based.information_retrieval.sources.canonical_knowledge import (
    get_canonical_evidence_and_requirements,
)
from agents.knowledge_based.information_retrieval.live_retrieval.live_fetcher import (
    LiveGovernmentFetcher,
    LiveRetrievalResult,
    LiveRetrievalStatus,
)
from agents.knowledge_based.information_retrieval.retrieval.retriever import VectorRetriever
from agents.knowledge_based.information_retrieval.retrieval.fusion import (
    EvidenceFusionEngine,
    FreshnessType,
)
from agents.knowledge_based.information_retrieval.retrieval.ranker import EvidenceRanker

from .supporting_requirements import FAQ_ID, FAQ_URL, service_key, supporting_requirements, passage_digest

logger = logging.getLogger(__name__)


class RetrievalMode(str, Enum):
    """Retrieval execution mode."""
    KNOWLEDGE_ONLY = "knowledge_only"
    LIVE_ONLY = "live_only"
    HYBRID = "hybrid"


class HybridRetriever:
    """
    Orchestrates hybrid retrieval from local ChromaDB vector knowledge base and official government HTTP live fetching,
    followed by evidence fusion, deterministic signal ranking, and grounding verification.
    """

    def __init__(
        self,
        vector_retriever: Optional[VectorRetriever] = None,
        live_fetcher: Optional[LiveGovernmentFetcher] = None,
        source_registry: Optional[SourceRegistry] = None,
        fusion_engine: Optional[EvidenceFusionEngine] = None,
        ranker: Optional[EvidenceRanker] = None,
        default_mode: RetrievalMode = RetrievalMode.HYBRID,
    ):
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.live_fetcher = live_fetcher or LiveGovernmentFetcher()
        self.source_registry = source_registry or SourceRegistry(include_defaults=True)
        self.fusion_engine = fusion_engine or EvidenceFusionEngine()
        self.ranker = ranker or EvidenceRanker(verifier=None)
        self.default_mode = default_mode

    def retrieve(
        self,
        request: RetrievalRequest,
        mode: Optional[RetrievalMode] = None,
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        """
        Executes retrieval according to chosen mode (KNOWLEDGE_ONLY, LIVE_ONLY, or HYBRID),
        fuses evidence, ranks candidates, and verifies grounding.
        """
        effective_mode = mode or self.default_mode

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

        knowledge_evidence: List[Evidence] = []
        live_evidence: List[Evidence] = []
        warnings: List[WarningItem] = []
        req_summaries: List[Dict[str, Any]] = []

        # 1. KNOWLEDGE RETRIEVAL PATH (ChromaDB)
        if effective_mode in (RetrievalMode.KNOWLEDGE_ONLY, RetrievalMode.HYBRID):
            try:
                know_res = self.vector_retriever.retrieve_for_request(request, top_k=top_k)
                if know_res and know_res.evidence:
                    knowledge_evidence.extend(know_res.evidence)
                if know_res and know_res.requirements:
                    req_summaries.extend(know_res.requirements)
                if know_res and know_res.warnings:
                    warnings.extend(know_res.warnings)
            except Exception as e:
                logger.error(f"Knowledge vector retrieval failed: {e}")
                warnings.append(
                    WarningItem(
                        warning_id="warn_knowledge_failed",
                        code="KNOWLEDGE_RETRIEVAL_FAILED",
                        message=f"ChromaDB vector retrieval failed: {str(e)}",
                    )
                )

        # 2. LIVE RETRIEVAL PATH (Live HTTP Fetcher)
        if effective_mode in (RetrievalMode.LIVE_ONLY, RetrievalMode.HYBRID):
            live_items, live_warns = self._execute_live_retrieval(request)
            live_evidence.extend(live_items)
            warnings.extend(live_warns)

        # 3. EVIDENCE FUSION & CONFLICT DETECTION
        fused_evidence, sources, conflicts = self.fusion_engine.fuse_evidence(
            knowledge_evidence=knowledge_evidence,
            live_evidence=live_evidence,
        )

        # 4. EVIDENCE RANKING & GROUNDING VERIFICATION
        ranked_evidence = self.ranker.rank_and_verify(fused_evidence)

        # 4b. CANONICAL FALLBACK FOR COLD-START / OFFLINE ENVIRONMENTS
        has_retrieved_evidence = bool(ranked_evidence)
        if (not ranked_evidence or not req_summaries or not has_retrieved_evidence) and (request.domain or "aadhaar").lower() == "aadhaar":
            target_key = request.service or request.goal or "address"
            can_ev, can_req, can_sources = get_canonical_evidence_and_requirements(target_key, "aadhaar")
            if not ranked_evidence or not has_retrieved_evidence:
                ranked_evidence = can_ev
                req_summaries = can_req
                sources = can_sources

        # Supporting requirements must come from captured service-specific source evidence.
        if request.domain == "aadhaar" and service_key(request.service):
            proven = supporting_requirements(request.service, ranked_evidence)
            if not proven:
                warnings.append(WarningItem(warning_id="warn_supporting_documents_unknown",
                    code="SUPPORTING_DOCUMENT_REQUIREMENTS_UNKNOWN",
                    message="No traceable service-specific UIDAI supporting-document evidence is available."))
            req_summaries = proven or [{
                "requirement_id": "uidai_supporting_documents_unknown",
                "category": "document", "service": service_key(request.service),
                "description": "Authoritative accepted-document evidence unavailable.",
                "grounding_status": "unverified", "evidence_ids": [],
                "accepted_document_types": [], "source_retrieved_at": None,
            }]
        # 5. DETERMINE RETRIEVAL STATUS
        if ranked_evidence:
            if effective_mode == RetrievalMode.HYBRID and (not live_evidence and knowledge_evidence):
                status = RetrievalStatus.PARTIAL_SUCCESS
            else:
                status = RetrievalStatus.SUCCESS
        else:
            status = RetrievalStatus.NO_EVIDENCE_FOUND

        return RetrievalResult(
            result_id=f"res_{request.request_id}",
            request_id=request.request_id,
            service=request.service,
            domain=request.domain,
            retrieval_status=status,
            requirements=req_summaries,
            evidence=ranked_evidence,
            sources=sources,
            conflicts=conflicts,
            warnings=warnings,
            metadata={
                "retrieval_mode": effective_mode.value,
                "knowledge_evidence_count": len(knowledge_evidence),
                "live_evidence_count": len(live_evidence),
                "fused_evidence_count": len(fused_evidence),
                "ranked_evidence_count": len(ranked_evidence),
                "conflicts_count": len(conflicts),
            },
        )

    def _execute_live_retrieval(self, request: RetrievalRequest) -> Tuple[List[Evidence], List[WarningItem]]:
        """
        Queries registered authoritative web sources live over HTTP for request domain.
        """
        live_evidence: List[Evidence] = []
        warnings: List[WarningItem] = []

        domain = request.domain or "aadhaar"
        auth_sources = self.source_registry.list_sources(domain=domain, active_only=True)

        if not auth_sources:
            warnings.append(
                WarningItem(
                    warning_id="warn_no_live_sources",
                    code="NO_LIVE_SOURCES_REGISTERED",
                    message=f"No active authoritative web sources registered for domain '{domain}'",
                )
            )
            return live_evidence, warnings

        if domain == "aadhaar" and service_key(request.service):
            source = Source(source_id=FAQ_ID, authority="UIDAI", domain="aadhaar",
                            url=FAQ_URL, document_title="UIDAI Aadhaar Online Services FAQ", last_checked="",
                            source_type=SourceType.OFFICIAL_FAQ)
            auth_sources = [source]

        # Attempt live fetching on primary portal source
        for source in auth_sources[:2]:  # Limit live fetch calls to top 2 registered sources
            # Verify authority before fetching
            if not self.source_registry.is_authoritative(source.url, domain):
                warnings.append(
                    WarningItem(
                        warning_id=f"warn_untrusted_{source.source_id}",
                        code="UNAUTHORIZED_SOURCE",
                        message=f"Source URL '{source.url}' rejected by authority filter",
                        source_id=source.source_id,
                    )
                )
                continue

            live_res: LiveRetrievalResult = self.live_fetcher.fetch_source(source)

            if live_res.status == LiveRetrievalStatus.SUCCESS and live_res.is_usable_content:
                source.last_checked = live_res.retrieved_at
                text = live_res.extracted_text or ""
                if source.source_id == FAQ_ID:
                    normalized = " ".join(text.split())
                    question = ("What documents can I submit to update document in Aadhaar?"
                                if service_key(request.service) == "document_update" else
                                "My online address update request got rejected for invalid documents. What does this mean?")
                    end = ("How can I submit the documents online?" if service_key(request.service) == "document_update"
                           else "Secure QR Code Reader")
                    if question not in normalized or end not in normalized.split(question, 1)[1]:
                        continue
                    text = question + normalized.split(question, 1)[1].split(end, 1)[0]
                else:
                    text = text[:1000]
                # Process requirement snippets
                ev_id = f"live_{source.source_id}_{int(datetime.now(timezone.utc).timestamp())}"
                evidence_item = Evidence(
                    evidence_id=ev_id,
                    claim=f"Live official web evidence for {request.service}",
                    passage=text,
                    source=source,
                    retrieved_at=live_res.retrieved_at,
                    confidence=1.0,
                    relevance_score=0.9,
                    metadata={
                        "freshness_type": FreshnessType.LIVE_CURRENT_RETRIEVAL.value,
                        "http_status_code": live_res.http_status_code,
                        "page_title": live_res.page_title,
                        "last_modified": live_res.last_modified,
                        "etag": live_res.etag,
                        "category": request.service,
                        "evidence_origin": "official_live",
                        "capture_kind": "http_response",
                        "captured_passage_sha256": passage_digest(text),
                        "effective_url": live_res.redirected_url or live_res.url,
                        "source_retrieved_at": live_res.retrieved_at,
                    },
                )
                live_evidence.append(evidence_item)

            else:
                # Log graceful fallback warning
                warnings.append(
                    WarningItem(
                        warning_id=f"warn_live_{source.source_id}",
                        code="LIVE_RETRIEVAL_FAILED",
                        message=f"Live retrieval from '{source.url}' ended with status '{live_res.status}': {live_res.error_message or 'Unusable content'}",
                        source_id=source.source_id,
                    )
                )

        return live_evidence, warnings
