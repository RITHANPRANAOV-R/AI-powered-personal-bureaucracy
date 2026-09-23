"""
Evidence Fusion and Conflict Detection module for Information Retrieval Agent.
Fuses candidate evidence from ChromaDB vector knowledge base, live government HTTP retrieval,
user uploaded documents, and requirement ↔ document links into a unified cross-evidence picture.
"""
import re
import logging
from enum import Enum
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone

from agents.knowledge_based.information_retrieval.schemas.source import Source
from agents.knowledge_based.information_retrieval.schemas.evidence import Evidence, GroundingStatus
from agents.knowledge_based.information_retrieval.schemas.retrieval_result import ConflictItem
from agents.knowledge_based.information_retrieval.schemas.user_document import UserDocument
from agents.knowledge_based.information_retrieval.schemas.linking import LinkingResult, LinkStatus

logger = logging.getLogger(__name__)


class FreshnessType(str, Enum):
    """Classification of evidence freshness and retrieval origin."""
    LIVE_CURRENT_RETRIEVAL = "live_current_retrieval"
    STORED_OFFICIAL_DOCUMENT = "stored_official_document"
    DOCUMENT_METADATA_TIMESTAMP = "document_metadata_timestamp"
    UNKNOWN_FRESHNESS = "unknown_freshness"


class EvidenceOrigin(str, Enum):
    """Classification of evidence source origins."""
    OFFICIAL_STORED = "official_stored"
    OFFICIAL_LIVE = "official_live"
    USER_DOCUMENT = "user_document"
    REQUIREMENT_DOCUMENT_LINK = "requirement_document_link"


class CoverageStatus(str, Enum):
    """Requirement evidence coverage classification."""
    SUPPORTED_BY_USER_EVIDENCE = "supported_by_user_evidence"
    PARTIALLY_SUPPORTED = "partially_supported"
    NO_USER_EVIDENCE = "no_user_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNKNOWN = "unknown"


def convert_user_document_to_evidence(user_doc: UserDocument) -> List[Evidence]:
    """
    Converts extracted fields from UserDocument into individual evidence items.
    Preserves authority boundary (user document != official government source).
    """
    evidence_items: List[Evidence] = []
    if not user_doc or not user_doc.extracted_fields:
        return evidence_items

    user_source = Source(
        source_id=f"src_udoc_{user_doc.document_id}",
        authority="User Document Upload",
        domain="user_document",
        url="",
        document_title=user_doc.filename,
        trust_level=0.5,
    )

    doc_type_str = user_doc.document_type.value if hasattr(user_doc.document_type, "value") else str(user_doc.document_type)
    method_str = user_doc.extraction_method.value if hasattr(user_doc.extraction_method, "value") else str(user_doc.extraction_method)
    ocr_str = user_doc.ocr_status.value if hasattr(user_doc.ocr_status, "value") else str(user_doc.ocr_status)

    for field_name, f_obj in user_doc.extracted_fields.items():
        ev_id = f"ev_udoc_{user_doc.document_id}_{field_name}"
        f_val = f_obj.value
        f_conf = getattr(f_obj, "confidence", 1.0)
        page_num = getattr(f_obj, "page_number", 1)

        evidence_items.append(
            Evidence(
                evidence_id=ev_id,
                claim=f"User Document Extracted Field: '{field_name}'",
                passage=f"Extracted {field_name}: '{f_val}' from uploaded document '{user_doc.filename}' (Type: {doc_type_str})",
                source=user_source,
                confidence=f_conf,
                relevance_score=0.8,
                ranking_score=0.0,  # Do not confuse OCR extraction confidence with RAG ranking score
                grounding_status=GroundingStatus.UNVERIFIED,  # User evidence is NOT official government grounded
                page_number=page_num,
                metadata={
                    "evidence_origin": EvidenceOrigin.USER_DOCUMENT.value,
                    "freshness_type": FreshnessType.DOCUMENT_METADATA_TIMESTAMP.value,
                    "document_id": user_doc.document_id,
                    "filename": user_doc.filename,
                    "document_type": doc_type_str,
                    "field_name": field_name,
                    "extraction_method": method_str,
                    "extraction_confidence": f_conf,
                    "ocr_status": ocr_str,
                },
            )
        )

    return evidence_items


def convert_linking_result_to_evidence(linking_result: LinkingResult) -> List[Evidence]:
    """
    Converts requirement-document candidate links into evidence items for cross-evidence synthesis.
    """
    evidence_items: List[Evidence] = []
    if not linking_result or not linking_result.links:
        return evidence_items

    linker_source = Source(
        source_id="src_req_linker",
        authority="Requirement Document Linker",
        domain="linking",
        url="",
        document_title="Requirement-Document Linker Output",
        trust_level=1.0,
    )

    for link in linking_result.links:
        link_status_str = link.status.value if hasattr(link.status, "value") else str(link.status)
        reasons_str = "; ".join(link.matching_reasons) if link.matching_reasons else "No explicit matching reason"

        evidence_items.append(
            Evidence(
                evidence_id=f"ev_link_{link.link_id}",
                claim=f"Requirement Candidate Link: {link.requirement_category} -> {link.matched_document_type or 'missing'}",
                passage=f"Requirement '{link.requirement_description}' link status is '{link_status_str}'. Details: {reasons_str}",
                source=linker_source,
                confidence=link.confidence,
                relevance_score=0.9,
                ranking_score=0.0,
                grounding_status=GroundingStatus.UNVERIFIED,
                metadata={
                    "evidence_origin": EvidenceOrigin.REQUIREMENT_DOCUMENT_LINK.value,
                    "freshness_type": FreshnessType.STORED_OFFICIAL_DOCUMENT.value,
                    "link_id": link.link_id,
                    "requirement_id": link.requirement_id,
                    "category": link.requirement_category,
                    "status": link_status_str,
                    "matched_document_id": link.matched_document_id,
                    "matched_document_type": link.matched_document_type,
                    "missing_fields": link.missing_fields,
                    "official_evidence_ids": link.official_evidence_ids,
                },
            )
        )

    return evidence_items


class ConflictDetector:
    """
    Scans candidate evidence for conflicting claims (e.g. differing fee amounts or timelines)
    on the same requirement topic.
    """

    CURRENCY_REGEX = re.compile(r"(?:rs\.?|rupees|₹)\s*(\d+)", re.IGNORECASE)
    DAYS_REGEX = re.compile(r"(\d+)\s*(?:working\s*)?days?", re.IGNORECASE)

    def detect_conflicts(self, evidence_list: List[Evidence]) -> List[ConflictItem]:
        """
        Scans candidate evidence items grouped by requirement category for value conflicts.
        """
        if not evidence_list or len(evidence_list) < 2:
            return []

        # Filter for official evidence items only to avoid misclassifying user uploads as official conflicts
        official_items = [
            ev for ev in evidence_list
            if ev.metadata.get("evidence_origin") in (EvidenceOrigin.OFFICIAL_STORED.value, EvidenceOrigin.OFFICIAL_LIVE.value, None)
        ]

        if len(official_items) < 2:
            return []

        by_category: Dict[str, List[Evidence]] = {}
        for ev in official_items:
            cat = ev.metadata.get("category", "general")
            by_category.setdefault(cat, []).append(ev)

        conflicts: List[ConflictItem] = []
        conflict_idx = 1

        for cat, items in by_category.items():
            if len(items) < 2:
                continue

            # 1. Check for fee amount discrepancies
            fee_values: List[Tuple[int, Evidence]] = []
            for item in items:
                matches = self.CURRENCY_REGEX.findall(item.passage)
                for m in matches:
                    try:
                        val = int(m)
                        fee_values.append((val, item))
                    except ValueError:
                        pass

            if fee_values:
                unique_amounts = set(v[0] for v in fee_values)
                if len(unique_amounts) > 1:
                    conflicting_evidence = [v[1] for v in fee_values]
                    conflicting_sources = list({ev.source.source_id: ev.source for ev in conflicting_evidence}.values())
                    amounts_str = ", ".join(f"Rs {a}" for a in sorted(unique_amounts))

                    conflicts.append(
                        ConflictItem(
                            conflict_id=f"conf_fee_{conflict_idx}",
                            topic=f"Fee amount discrepancy in category '{cat}'",
                            description=f"Multiple authoritative sources state conflicting fee amounts ({amounts_str}) for requirement category '{cat}'",
                            sources=conflicting_sources,
                            evidence_list=conflicting_evidence,
                        )
                    )
                    conflict_idx += 1

            # 2. Check for timeline day discrepancies
            days_values: List[Tuple[int, Evidence]] = []
            for item in items:
                matches = self.DAYS_REGEX.findall(item.passage)
                for m in matches:
                    try:
                        val = int(m)
                        days_values.append((val, item))
                    except ValueError:
                        pass

            if days_values:
                unique_days = set(v[0] for v in days_values)
                if len(unique_days) > 1:
                    conflicting_evidence = [v[1] for v in days_values]
                    conflicting_sources = list({ev.source.source_id: ev.source for ev in conflicting_evidence}.values())
                    days_str = ", ".join(f"{d} days" for d in sorted(unique_days))

                    conflicts.append(
                        ConflictItem(
                            conflict_id=f"conf_days_{conflict_idx}",
                            topic=f"Service timeline discrepancy in category '{cat}'",
                            description=f"Multiple authoritative sources state conflicting delivery timelines ({days_str}) for category '{cat}'",
                            sources=conflicting_sources,
                            evidence_list=conflicting_evidence,
                        )
                    )
                    conflict_idx += 1

        return conflicts


class EvidenceFusionEngine:
    """
    Extended Phase 13 Fusion Engine.
    Fuses official stored RAG evidence, official live web evidence, user document evidence,
    and requirement-document links into a unified cross-evidence picture.
    """

    def __init__(self, conflict_detector: Optional[ConflictDetector] = None):
        self.conflict_detector = conflict_detector or ConflictDetector()

    def fuse_evidence(
        self,
        knowledge_evidence: List[Evidence],
        live_evidence: List[Evidence],
        user_documents: Optional[List[UserDocument]] = None,
        linking_result: Optional[LinkingResult] = None,
    ) -> Tuple[List[Evidence], List[Source], List[ConflictItem]]:
        """
        Merges official stored knowledge base evidence, live web evidence, user document evidence,
        and requirement links into a unified evidence set with full provenance annotations.
        """
        fused_evidence: List[Evidence] = []
        sources_dict: Dict[str, Source] = {}

        # 1. Process Official Stored Knowledge Evidence
        for ev in (knowledge_evidence or []):
            ev.metadata["evidence_origin"] = EvidenceOrigin.OFFICIAL_STORED.value
            ev.metadata["freshness_type"] = FreshnessType.STORED_OFFICIAL_DOCUMENT.value
            fused_evidence.append(ev)
            if ev.source and ev.source.source_id:
                sources_dict[ev.source.source_id] = ev.source

        # 2. Process Official Live Evidence
        for ev in (live_evidence or []):
            ev.metadata["evidence_origin"] = EvidenceOrigin.OFFICIAL_LIVE.value
            ev.metadata["freshness_type"] = FreshnessType.LIVE_CURRENT_RETRIEVAL.value
            fused_evidence.append(ev)
            if ev.source and ev.source.source_id:
                sources_dict[ev.source.source_id] = ev.source

        # 3. Process User Documents Evidence (if provided)
        if user_documents:
            for udoc in user_documents:
                udoc_ev_list = convert_user_document_to_evidence(udoc)
                for uev in udoc_ev_list:
                    fused_evidence.append(uev)
                    if uev.source and uev.source.source_id:
                        sources_dict[uev.source.source_id] = uev.source

        # 4. Process Requirement-Document Links (if provided)
        coverage_map: Dict[str, str] = {}
        if linking_result:
            link_ev_list = convert_linking_result_to_evidence(linking_result)
            for lev in link_ev_list:
                fused_evidence.append(lev)
                if lev.source and lev.source.source_id:
                    sources_dict[lev.source.source_id] = lev.source

            # Build requirement coverage status mapping
            if linking_result.links:
                for link in linking_result.links:
                    l_status = link.status.value if hasattr(link.status, "value") else str(link.status)
                    if l_status == LinkStatus.CANDIDATE_MATCH.value:
                        cov = CoverageStatus.SUPPORTED_BY_USER_EVIDENCE.value
                    elif l_status == LinkStatus.PARTIAL_MATCH.value:
                        cov = CoverageStatus.PARTIALLY_SUPPORTED.value
                    elif l_status == LinkStatus.MISSING_DOCUMENT.value:
                        cov = CoverageStatus.NO_USER_EVIDENCE.value
                    elif l_status == LinkStatus.CONFLICT.value:
                        cov = CoverageStatus.CONFLICTING_EVIDENCE.value
                    else:
                        cov = CoverageStatus.UNKNOWN.value
                    coverage_map[link.requirement_id] = cov

        # Annotate coverage status onto official requirement evidence items
        for ev in fused_evidence:
            req_id = ev.metadata.get("requirement_id") or f"req_ev_{ev.metadata.get('category', 'general')}"
            if req_id in coverage_map:
                ev.metadata["coverage_status"] = coverage_map[req_id]

        # 5. Detect Official Source Conflicts
        conflicts = self.conflict_detector.detect_conflicts(fused_evidence)

        # Merge inter-document user conflicts from linking_result (if present)
        if linking_result and linking_result.conflicts:
            for idx, u_conf in enumerate(linking_result.conflicts, start=1):
                conflicts.append(
                    ConflictItem(
                        conflict_id=f"conf_user_doc_{idx}",
                        topic=f"User Document Field Conflict: {u_conf.get('field_name', 'unknown')}",
                        description=u_conf.get("description", "Conflicting values across uploaded user documents"),
                        sources=[],
                        evidence_list=[],
                    )
                )

        return fused_evidence, list(sources_dict.values()), conflicts
