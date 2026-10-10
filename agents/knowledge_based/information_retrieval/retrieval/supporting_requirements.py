"""Supporting requirements derived only from captured UIDAI FAQ evidence."""
import hashlib
import re
from urllib.parse import urlparse
from agents.knowledge_based.information_retrieval.schemas.evidence import GroundingStatus
FAQ_URL = "https://uidai.gov.in/kn/aadhaar-online-services"
FAQ_ID = "src_uidai_supporting_documents_faq"


def service_key(service):
    text = re.sub(r"[^a-z0-9]+", "_", (service or "").lower()).strip("_")
    if text in {"document_update", "update_document", "aadhaar_document_update"}:
        return "document_update"
    if text in {"address", "update_address", "address_update", "aadhaar_address_update"}:
        return "address_update"
    return None


def passage_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def traceable(evidence):
    meta = evidence.metadata
    effective = urlparse(meta.get("effective_url", ""))
    original = urlparse(evidence.source.url or "")
    return bool(meta.get("evidence_origin") == "official_live"
        and meta.get("http_status_code") == 200
        and meta.get("capture_kind") == "http_response"
        and meta.get("captured_passage_sha256") == passage_digest(evidence.passage)
        and effective.scheme == original.scheme == "https"
        and effective.hostname == original.hostname
        and meta.get("source_retrieved_at") == evidence.retrieved_at)


def supporting_requirements(service, evidence_items):
    """Partial type lists: omission is UNKNOWN. Acceptance never verifies a document."""
    key = service_key(service)
    if not key:
        return []
    requirements = []
    for ev in evidence_items:
        if (ev.source.source_id != FAQ_ID or ev.source.url != FAQ_URL
                or ev.grounding_status != GroundingStatus.VERIFIED_GROUNDED
                or not traceable(ev)):
            continue
        text = " ".join(ev.passage.split())
        if key == "address_update":
            if "My online address update request got rejected for invalid documents. What does this mean?" not in text:
                continue
            if "Proof of Address" not in text or "Document is in the name of the Aadhaar holder" not in text:
                continue
            specs = [("proof_of_address", [], [])]
        else:
            if "What documents can I submit to update document in Aadhaar?" not in text:
                continue
            markers = ["Some common documents accepted as both POI and POA:",
                       "Some common documents accepted as POI only:",
                       "Some common documents accepted as POA only:"]
            if (not all(text.count(marker) == 1 for marker in markers)
                    or [text.index(marker) for marker in markers] != sorted(text.index(marker) for marker in markers)
                    or "To update document, you have to submit your Proof of Identity (POI) and Proof of Address (POA)." not in text):
                continue
            both = text.split(markers[0], 1)[1].split(markers[1], 1)[0].lower()
            poi = text.split(markers[1], 1)[1].split(markers[2], 1)[0].lower()
            common = [kind for phrase, kind in [("indian passport", "passport"),
                       ("voter identity card", "voter_id")] if phrase in both]
            identity_only = [kind for phrase, kind in [("pan/e-pan card", "pan"),
                             ("driving license", "driving_licence")] if phrase in poi]
            specs = [("proof_of_identity", common + identity_only, []),
                     ("proof_of_address", common, identity_only)]
        for category, accepted, excluded in specs:
            requirements.append({
                "requirement_id": f"uidai_{key}_{category}", "category": category,
                "service": key, "description": f"UIDAI {category.replace('_', ' ')} requirement for {key}.",
                "accepted_document_types": accepted, "not_accepted_document_types": excluded,
                "document_list_complete": False, "eligibility_scope": "document_type_only",
                "grounding_status": GroundingStatus.VERIFIED_GROUNDED.value,
                "evidence_ids": [ev.evidence_id], "source_id": ev.source.source_id,
                "source_url": ev.source.url, "source_retrieved_at": ev.retrieved_at,
                "freshness_type": ev.metadata.get("freshness_type"),
                "conditions": "Passport means Indian passport only. Citizen document nationality, authenticity, validity and required content are not verified.",
            })
    return requirements
