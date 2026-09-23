"""
Requirement to User Document Linker.
Deterministically maps official government requirements against user document evidence,
identifying candidate matches, missing document gaps, missing fields, and inter-document conflicts.
"""
import uuid
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

from agents.knowledge_based.information_retrieval.schemas.retrieval_result import RetrievalResult
from agents.knowledge_based.information_retrieval.schemas.user_document import UserDocument, DocumentType
from agents.knowledge_based.information_retrieval.schemas.linking import (
    LinkingResult,
    RequirementDocumentLink,
    LinkStatus,
)

logger = logging.getLogger(__name__)


class RequirementDocumentLinker:
    """
    Deterministic Linker connecting official RetrievalResult requirements to user document evidence.
    Does NOT make legal/compliance claims; produces inspectable candidate relationships.
    """

    CATEGORY_MAP = {
        "address": {
            "doc_types": [DocumentType.AADHAAR, DocumentType.PASSPORT, DocumentType.VOTER_ID, DocumentType.DRIVING_LICENCE, DocumentType.ADDRESS_PROOF],
            "fields": ["address"],
        },
        "identity": {
            "doc_types": [DocumentType.AADHAAR, DocumentType.PASSPORT, DocumentType.VOTER_ID, DocumentType.PAN, DocumentType.IDENTITY_PROOF],
            "fields": ["name"],
        },
        "dob": {
            "doc_types": [DocumentType.AADHAAR, DocumentType.PASSPORT, DocumentType.PAN, DocumentType.VOTER_ID],
            "fields": ["dob"],
        },
        "eligibility": {
            "doc_types": [DocumentType.AADHAAR, DocumentType.PASSPORT, DocumentType.VOTER_ID, DocumentType.PAN, DocumentType.IDENTITY_PROOF],
            "fields": ["name"],
        },
    }

    def link(
        self,
        retrieval_result: RetrievalResult,
        user_documents: List[UserDocument],
    ) -> LinkingResult:
        """
        Executes requirement ↔ document candidate linking and inter-document conflict scanning.
        """
        session_id = f"link_{uuid.uuid4().hex[:12]}"
        req_id = retrieval_result.request_id if retrieval_result else "unknown"

        if not retrieval_result:
            return LinkingResult(
                linking_id=session_id,
                request_id=req_id,
                warnings=["RetrievalResult is null"],
            )

        links: List[RequirementDocumentLink] = []
        uncovered: List[str] = []
        warnings: List[str] = []

        # 1. Extract Requirements from RetrievalResult
        raw_reqs = retrieval_result.requirements or []

        # Fallback to evidence categories if requirements list is empty
        if not raw_reqs and retrieval_result.evidence:
            seen_cats: Set[str] = set()
            for ev in retrieval_result.evidence:
                cat = str(ev.metadata.get("category", "general")).lower()
                if cat not in seen_cats:
                    seen_cats.add(cat)
                    raw_reqs.append({
                        "requirement_id": f"req_ev_{cat}",
                        "category": cat,
                        "description": f"Evidence requirement for {cat}",
                    })

        if not raw_reqs:
            warnings.append("RetrievalResult contains zero explicit requirements or evidence categories")
            return LinkingResult(
                linking_id=session_id,
                request_id=req_id,
                warnings=warnings,
            )

        # Collect official evidence ID map
        evidence_by_category: Dict[str, List[str]] = {}
        if retrieval_result.evidence:
            for ev in retrieval_result.evidence:
                cat = str(ev.metadata.get("category", "")).lower()
                if cat:
                    evidence_by_category.setdefault(cat, []).append(ev.evidence_id)

        # 2. Process Requirement Matching
        for req_dict in raw_reqs:
            r_id = req_dict.get("requirement_id", f"req_{len(links)+1}")
            r_cat = str(req_dict.get("category", "general")).lower()
            r_desc = req_dict.get("description", f"Requirement for {r_cat}")

            # Identify target doc types and required fields
            target_types, target_fields = self._resolve_target_specs(r_cat, r_desc)

            matched_link = self._match_candidate_documents(
                r_id=r_id,
                r_cat=r_cat,
                r_desc=r_desc,
                target_types=target_types,
                target_fields=target_fields,
                user_documents=user_documents,
                official_evidence_ids=evidence_by_category.get(r_cat, []),
            )

            links.append(matched_link)
            if matched_link.status == LinkStatus.MISSING_DOCUMENT:
                uncovered.append(r_id)

        # 3. Inter-Document Conflict Scanning
        conflicts = self._detect_user_document_conflicts(user_documents)

        return LinkingResult(
            linking_id=session_id,
            request_id=req_id,
            links=links,
            uncovered_requirements=uncovered,
            conflicts=conflicts,
            warnings=warnings,
        )

    def _resolve_target_specs(self, category: str, description: str) -> Tuple[List[DocumentType], List[str]]:
        """Resolves target compatible document types and required fields for requirement."""
        desc_lower = description.lower()

        for key, spec in self.CATEGORY_MAP.items():
            if key in category or key in desc_lower:
                return spec["doc_types"], spec["fields"]

        # Default fallback for generic service requirement
        all_valid_types = [
            DocumentType.AADHAAR, DocumentType.PASSPORT, DocumentType.VOTER_ID,
            DocumentType.PAN, DocumentType.DRIVING_LICENCE, DocumentType.ADDRESS_PROOF, DocumentType.IDENTITY_PROOF
        ]
        return all_valid_types, []

    def _match_candidate_documents(
        self,
        r_id: str,
        r_cat: str,
        r_desc: str,
        target_types: List[DocumentType],
        target_fields: List[str],
        user_documents: List[UserDocument],
        official_evidence_ids: List[str],
    ) -> RequirementDocumentLink:
        """Evaluates user documents against requirement specs."""
        link_id = f"link_{r_id}"

        if not user_documents:
            return RequirementDocumentLink(
                link_id=link_id,
                requirement_id=r_id,
                requirement_category=r_cat,
                requirement_description=r_desc,
                status=LinkStatus.MISSING_DOCUMENT,
                matching_reasons=["No user documents uploaded"],
                official_evidence_ids=official_evidence_ids,
                confidence=0.0,
            )

        # Helper string converter
        def to_str(val: Any) -> str:
            return val.value if hasattr(val, "value") else str(val)

        target_type_strs = [to_str(dt) for dt in target_types]

        # Search for compatible candidate document
        candidate_doc: Optional[UserDocument] = None
        for doc in user_documents:
            doc_type_str = to_str(doc.document_type)
            if doc_type_str in target_type_strs:
                candidate_doc = doc
                break

        if not candidate_doc:
            return RequirementDocumentLink(
                link_id=link_id,
                requirement_id=r_id,
                requirement_category=r_cat,
                requirement_description=r_desc,
                status=LinkStatus.MISSING_DOCUMENT,
                matching_reasons=[f"No user document found matching compatible types: {target_type_strs}"],
                official_evidence_ids=official_evidence_ids,
                confidence=0.0,
            )

        # Check field presence and confidence
        matched_fields = []
        missing_fields = []
        matching_reasons = [f"Candidate document '{candidate_doc.filename}' (Type: {to_str(candidate_doc.document_type)}) is compatible"]

        for req_f in target_fields:
            if req_f in candidate_doc.extracted_fields:
                ext_f = candidate_doc.extracted_fields[req_f]
                f_conf = getattr(ext_f, "confidence", 1.0)
                if f_conf >= 0.60:
                    matched_fields.append({
                        "field_name": req_f,
                        "value": ext_f.value,
                        "confidence": f_conf,
                        "page_number": getattr(ext_f, "page_number", 1),
                    })
                    matching_reasons.append(f"Required field '{req_f}' present with confidence {f_conf}")
                else:
                    missing_fields.append(req_f)
                    matching_reasons.append(f"Required field '{req_f}' present but confidence ({f_conf}) is low (< 0.60)")
            else:
                missing_fields.append(req_f)
                matching_reasons.append(f"Required field '{req_f}' is absent from candidate document")

        # Determine Link Status
        if target_fields and missing_fields:
            status = LinkStatus.PARTIAL_MATCH
            link_conf = 0.50
        else:
            status = LinkStatus.CANDIDATE_MATCH
            link_conf = candidate_doc.overall_confidence

        return RequirementDocumentLink(
            link_id=link_id,
            requirement_id=r_id,
            requirement_category=r_cat,
            requirement_description=r_desc,
            status=status,
            matched_document_id=candidate_doc.document_id,
            matched_document_type=to_str(candidate_doc.document_type),
            matched_fields=matched_fields,
            missing_fields=missing_fields,
            matching_reasons=matching_reasons,
            official_evidence_ids=official_evidence_ids,
            confidence=round(link_conf, 4),
            metadata={
                "filename": candidate_doc.filename,
                "extraction_method": to_str(candidate_doc.extraction_method),
            },
        )

    def _detect_user_document_conflicts(self, user_documents: List[UserDocument]) -> List[Dict[str, Any]]:
        """Scans user documents for conflicting field values across multiple files."""
        conflicts: List[Dict[str, Any]] = []
        if len(user_documents) < 2:
            return conflicts

        field_occurrences: Dict[str, List[Dict[str, Any]]] = {}

        for doc in user_documents:
            for f_name, f_obj in doc.extracted_fields.items():
                if f_name in ("name", "dob", "address"):
                    clean_val = f_obj.value.strip().lower()
                    field_occurrences.setdefault(f_name, []).append({
                        "document_id": doc.document_id,
                        "filename": doc.filename,
                        "raw_value": f_obj.value,
                        "clean_value": clean_val,
                        "confidence": f_obj.confidence,
                    })

        for f_name, occurrences in field_occurrences.items():
            if len(occurrences) >= 2:
                distinct_values = set(item["clean_value"] for item in occurrences)
                if len(distinct_values) > 1:
                    conflicts.append({
                        "conflict_id": f"conf_{f_name}_{uuid.uuid4().hex[:6]}",
                        "field_name": f_name,
                        "description": f"Conflicting values detected for field '{f_name}' across user documents",
                        "competing_records": occurrences,
                    })
                    logger.info(f"Conflict detected across user documents for field '{f_name}'")

        return conflicts
