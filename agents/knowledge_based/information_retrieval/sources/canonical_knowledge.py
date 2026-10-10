"""
Local canonical fallback claims, not captured or verified UIDAI evidence.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from copy import deepcopy
from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType
from agents.knowledge_based.information_retrieval.schemas.evidence import Evidence, GroundingStatus

UIDAI_OFFICIAL_SOURCE = Source(
    source_id="uidai-official-portal",
    authority="UIDAI",
    domain="aadhaar",
    source_type=SourceType.OFFICIAL_FAQ,
    document_title="UIDAI Official Updating Data Guidelines",
    url="https://uidai.gov.in/en/my-aadhaar/about-your-aadhaar/updating-data-on-aadhaar.html",
    trust_level=1.0,
    last_checked="",
    freshness_policy="unknown",
)

CANONICAL_SERVICES: Dict[str, Dict[str, Any]] = {
    "address": {
        "service_name": "Aadhaar Address Update",
        "evidence": [
            Evidence(
                evidence_id="ev-uidai-address-proof",
                claim="Proof of Address (PoA) is strictly required for updating address in Aadhaar records.",
                passage="To update address online via UIDAI Self Service Update Portal (SSUP), a resident must upload a valid supporting Proof of Address document from the approved list (e.g. Passport, Bank Statement/Passbook, Ration Card, Voter ID, Electricity Bill).",
                source=UIDAI_OFFICIAL_SOURCE,
                grounding_status=GroundingStatus.UNVERIFIED,
                retrieved_at="",
                confidence=1.0,
                relevance_score=1.0,
                metadata={"category": "document", "associated_requirements": ["address-proof"]},
            )
        ],
        "requirements": [
            {
                "requirement_id": "address-proof",
                "category": "document",
                "description": "Upload a valid Proof of Address document.",
                "evidence_ids": ["ev-uidai-address-proof"],
                "required_document_refs": ["address-proof"],
                "required_fact_keys": ["address"],
            }
        ],
    },
    "name": {
        "service_name": "Aadhaar Name Correction",
        "evidence": [
            Evidence(
                evidence_id="ev-uidai-poi",
                claim="Proof of Identity (PoI) with photo is required for updating resident name in Aadhaar.",
                passage="UIDAI guidelines permit minor name corrections online with valid Proof of Identity containing name and photograph (e.g. Passport, PAN Card, Voter ID Card, Driving License).",
                source=UIDAI_OFFICIAL_SOURCE,
                grounding_status=GroundingStatus.UNVERIFIED,
                retrieved_at="",
                confidence=1.0,
                relevance_score=1.0,
                metadata={"category": "document", "associated_requirements": ["identity-proof"]},
            )
        ],
        "requirements": [
            {
                "requirement_id": "identity-proof",
                "category": "document",
                "description": "Upload a valid Proof of Identity document with photograph.",
                "evidence_ids": ["ev-uidai-poi"],
                "required_document_refs": ["identity-proof"],
                "required_fact_keys": ["name"],
            }
        ],
    },
    "date_of_birth": {
        "service_name": "Aadhaar Date of Birth Update",
        "evidence": [
            Evidence(
                evidence_id="ev-uidai-dob-proof",
                claim="Official Proof of Date of Birth is required for updating date of birth in Aadhaar.",
                passage="Date of Birth update is permitted once in a lifetime with authoritative proof such as Birth Certificate, SSLC Book/Certificate, or Passport.",
                source=UIDAI_OFFICIAL_SOURCE,
                grounding_status=GroundingStatus.UNVERIFIED,
                retrieved_at="",
                confidence=1.0,
                relevance_score=1.0,
                metadata={"category": "document", "associated_requirements": ["dob-proof"]},
            )
        ],
        "requirements": [
            {
                "requirement_id": "dob-proof",
                "category": "document",
                "description": "Upload an authoritative Date of Birth proof document.",
                "evidence_ids": ["ev-uidai-dob-proof"],
                "required_document_refs": ["dob-proof"],
                "required_fact_keys": ["date_of_birth"],
            }
        ],
    },
    "status_inquiry": {
        "service_name": "Aadhaar Status Inquiry",
        "evidence": [
            Evidence(
                evidence_id="ev-uidai-status-guide",
                claim="Aadhaar update status can be tracked using 14-digit URN or SRN.",
                passage="Residents who have submitted an Aadhaar update request can track current status using their 14-digit Update Request Number (URN) on the UIDAI portal.",
                source=UIDAI_OFFICIAL_SOURCE,
                grounding_status=GroundingStatus.UNVERIFIED,
                retrieved_at="",
                confidence=1.0,
                relevance_score=1.0,
                metadata={"category": "information", "associated_requirements": ["urn-reference"]},
            )
        ],
        "requirements": [
            {
                "requirement_id": "urn-reference",
                "category": "information",
                "description": "Provide Update Request Number (URN) to check processing status.",
                "evidence_ids": ["ev-uidai-status-guide"],
                "required_fact_keys": ["urn"],
            }
        ],
    },
}


def get_canonical_evidence_and_requirements(
    service_or_target: str | None,
    domain: str = "aadhaar",
) -> Tuple[List[Evidence], List[Dict[str, Any]], List[Source]]:
    """
    Returns canonical evidence, requirements, and sources for a given service.
    Normalizes service keys (e.g. 'address', 'update_address', 'Aadhaar') to ensure a match.
    """
    for spec in CANONICAL_SERVICES.values():
        for ev in spec["evidence"]:
            ev.metadata.update({"evidence_origin": "static_canonical", "freshness_type": "unknown_freshness", "source_retrieved_at": None, "verification_note": "Local fallback; source content has not been verified."})
        for req in spec["requirements"]:
            req.update({"grounding_status": "unverified", "freshness_type": "unknown_freshness", "source_retrieved_at": None})
    key = (service_or_target or "").lower()
    for supported in ("address", "name", "date_of_birth", "dob", "status_inquiry"):
        if supported in key:
            matched_key = "date_of_birth" if supported == "dob" else supported
            spec = CANONICAL_SERVICES.get(matched_key, CANONICAL_SERVICES["address"])
            return deepcopy(spec["evidence"]), deepcopy(spec["requirements"]), [UIDAI_OFFICIAL_SOURCE.model_copy(deep=True)]

    return [], [], []
