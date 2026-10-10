"""Phase 4: local captures only; no browser, government actions or vector store."""
from unittest.mock import Mock
import pytest
from agents.knowledge_based.information_retrieval.schemas.evidence import Evidence, GroundingStatus
from agents.knowledge_based.information_retrieval.schemas.source import Source
from agents.knowledge_based.information_retrieval.schemas.retrieval_request import RetrievalRequest
from agents.knowledge_based.information_retrieval.schemas.retrieval_result import RetrievalResult
from agents.knowledge_based.information_retrieval.schemas.user_document import UserDocument, ExtractedField
from agents.knowledge_based.information_retrieval.retrieval.supporting_requirements import (
    FAQ_ID, FAQ_URL, supporting_requirements, passage_digest)
from agents.knowledge_based.information_retrieval.retrieval.ranker import GroundingVerifier
from agents.knowledge_based.information_retrieval.retrieval.linker import RequirementDocumentLinker
from agents.knowledge_based.information_retrieval.retrieval.fusion import EvidenceFusionEngine
from agents.knowledge_based.information_retrieval.retrieval.hybrid_retriever import HybridRetriever, RetrievalMode
from agents.knowledge_based.information_retrieval.live_retrieval.live_fetcher import LiveRetrievalResult, LiveRetrievalStatus
from agents.knowledge_based.information_retrieval.sources.canonical_knowledge import get_canonical_evidence_and_requirements

# Short local fixture matching the observed FAQ structure, not a complete document list.
ANSWER = ("What documents can I submit to update document in Aadhaar? "
          "To update document, you have to submit your Proof of Identity (POI) and Proof of Address (POA). "
          "Some common documents accepted as both POI and POA: Voter identity card Indian passport "
          "Some common documents accepted as POI only: PAN/e-PAN card Driving license "
          "Some common documents accepted as POA only: Electricity bill")
STAMP = "2026-01-01T00:00:00+00:00"  # Explicit synthetic test timestamp.


def capture(text=ANSWER):
    ev = Evidence(evidence_id="capture", claim="FAQ answer", passage=text,
        source=Source(source_id=FAQ_ID, authority="UIDAI", domain="aadhaar", url=FAQ_URL),
        retrieved_at=STAMP, metadata={"category": "document_update", "evidence_origin": "official_live",
        "freshness_type": "live_current_retrieval", "http_status_code": 200,
        "effective_url": FAQ_URL, "capture_kind": "http_response", "source_retrieved_at": STAMP,
        "captured_passage_sha256": passage_digest(text)})
    ev.grounding_status = GroundingVerifier().verify_grounding(ev)
    return ev


def result(ev=None, service="document_update"):
    ev = ev or capture()
    return RetrievalResult(result_id="result", request_id="request", service=service, domain="aadhaar",
        requirements=supporting_requirements(service, [ev]), evidence=[ev], sources=[ev.source])


def document(kind, fields=True):
    return UserDocument(document_id="citizen", filename="synthetic.pdf", mime_type="application/pdf",
        document_type=kind, classification_confidence=1, ocr_status="success",
        extracted_fields={"address": ExtractedField(field_name="address", value="Synthetic address")} if fields else {})


def validations(res, doc):
    return [link.metadata["requirement_validation"] for link in RequirementDocumentLinker().link(res, [doc]).links]


def test_authoritative_requirements_preserve_service_evidence_and_freshness():
    res = result()
    assert len(res.requirements) == 2
    for req in res.requirements:
        assert req["service"] == "document_update"
        assert req["source_id"] == FAQ_ID and req["source_url"] == FAQ_URL
        assert req["evidence_ids"] == ["capture"] and req["source_retrieved_at"] == STAMP
        assert req["grounding_status"] == "verified_grounded"
        assert req["document_list_complete"] is False
        assert "steps" not in req and "procedure" not in req


@pytest.mark.parametrize("kind,expected", [("passport", ["accepted", "accepted"]),
    ("voter_id", ["accepted", "accepted"]), ("pan", ["accepted", "not_accepted"]),
    ("driving_licence", ["accepted", "not_accepted"]), ("aadhaar", ["unknown", "unknown"]),
    ("address_proof", ["unknown", "unknown"]), ("unknown", ["unknown", "unknown"])])
def test_type_eligibility_is_service_category_and_evidence_specific(kind, expected):
    checks = validations(result(), document(kind))
    assert [v["status"] for v in checks] == expected
    assert all(v["document_verified"] is False for v in checks)
    assert all(v["scope"] == "document_type_only" for v in checks)
    assert all(v["document_eligibility"] == "unknown" and not v["conditions_verified"] for v in checks)


def test_ocr_content_and_classification_do_not_verify_document():
    assert [v["status"] for v in validations(result(), document("aadhaar"))] == ["unknown", "unknown"]
    assert all(v["document_verified"] is False for v in validations(result(), document("passport", False)))


@pytest.mark.parametrize("service", ["address_update", "enrolment", "name", "unrecognized"])
def test_document_update_evidence_is_not_reused_for_other_services(service):
    assert supporting_requirements(service, [capture()]) == []


@pytest.mark.parametrize("change", ["missing_capture", "changed_passage", "redirect", "failed_http", "static"])
def test_unestablished_evidence_is_not_verified(change):
    ev = capture()
    if change == "missing_capture": ev.metadata.pop("capture_kind")
    if change == "changed_passage": ev.passage += " changed"
    if change == "redirect": ev.metadata["effective_url"] = "https://example.com/"
    if change == "failed_http": ev.metadata["http_status_code"] = 503
    if change == "static": ev.metadata["evidence_origin"] = "static_canonical"
    ev.grounding_status = GroundingVerifier().verify_grounding(ev)
    assert ev.grounding_status != "verified_grounded"
    assert supporting_requirements("document_update", [ev]) == []
    res = result()
    res.evidence = [ev]
    assert all(v["status"] == "unknown" for v in validations(res, document("passport")))


def test_requirement_metadata_alone_cannot_grant_acceptance():
    res = result()
    res.evidence = []
    assert all(v["status"] == "unknown" for v in validations(res, document("passport")))


def test_service_and_category_mismatch_cannot_grant_acceptance():
    res = result()
    for req in res.requirements: req["service"] = "address_update"
    assert all(v["status"] == "unknown" for v in validations(res, document("passport")))


def test_provenance_survives_link_and_cross_fusion_without_freshness_rewrite():
    res = result()
    links = RequirementDocumentLinker().link(res, [document("passport")])
    fused, _, _ = EvidenceFusionEngine().fuse_evidence(res.evidence, [], linking_result=links)
    assert fused[0].metadata["evidence_origin"] == "official_live"
    assert fused[0].metadata["freshness_type"] == "live_current_retrieval"
    assert fused[1].metadata["freshness_type"] == "unknown_freshness"
    linked = fused[1].metadata["requirement_validation"]
    assert linked["evidence"][0]["source"]["url"] == FAQ_URL
    assert linked["evidence"][0]["passage"] == ANSWER
    assert linked["requirement"]["source_retrieved_at"] == STAMP


def test_static_fallback_remains_unverified_after_ranking_and_fusion():
    evidence, reqs, _ = get_canonical_evidence_and_requirements("address")
    fused, _, _ = EvidenceFusionEngine().fuse_evidence(evidence, [])
    for ev in fused:
        assert ev.grounding_status == "unverified"
        assert GroundingVerifier().verify_grounding(ev) == GroundingStatus.UNVERIFIED
        assert ev.metadata["source_retrieved_at"] is None
        assert ev.metadata["freshness_type"] == "unknown_freshness"
    assert all(req["grounding_status"] == "unverified" for req in reqs)
    evidence[0].metadata["mutated"] = True
    assert "mutated" not in get_canonical_evidence_and_requirements("address")[0][0].metadata
    assert get_canonical_evidence_and_requirements("unrecognized") == ([], [], [])


def hybrid(fetcher):
    return HybridRetriever(vector_retriever=Mock(), live_fetcher=fetcher)


def test_actual_hybrid_path_uses_bounded_answer_and_never_calls_vector_in_live_only():
    fetcher = Mock()
    fetcher.fetch_source.return_value = LiveRetrievalResult(source_id=FAQ_ID, authority="UIDAI", url=FAQ_URL,
        status=LiveRetrievalStatus.SUCCESS, http_status_code=200, retrieved_at=STAMP,
        extracted_text="Unrelated header " + ANSWER + " How can I submit the documents online? Unrelated instructions",
        is_usable_content=True)
    retriever = hybrid(fetcher)
    res = retriever.retrieve(RetrievalRequest(request_id="request", goal="Synthetic requirement lookup", service="document_update", domain="aadhaar"), mode=RetrievalMode.LIVE_ONLY)
    assert len(res.requirements) == 2
    assert res.evidence[0].passage == ANSWER + " "
    assert res.procedure == []
    retriever.vector_retriever.retrieve_for_request.assert_not_called()
    assert fetcher.fetch_source.call_count == 1


def test_failed_fetch_returns_unknown_without_canonical_acceptance():
    fetcher = Mock()
    fetcher.fetch_source.return_value = LiveRetrievalResult(source_id=FAQ_ID, authority="UIDAI", url=FAQ_URL,
        status=LiveRetrievalStatus.SOURCE_UNAVAILABLE, is_usable_content=False)
    res = hybrid(fetcher).retrieve(RetrievalRequest(request_id="request", goal="Synthetic requirement lookup", service="address", domain="aadhaar"), mode=RetrievalMode.LIVE_ONLY)
    assert res.requirements[0]["grounding_status"] == "unverified"
    assert validations(res, document("passport"))[0]["status"] == "unknown"


def test_address_requirement_is_grounded_but_document_types_are_unknown():
    text = ("My online address update request got rejected for invalid documents. What does this mean? "
            "The Proof of Address document should be valid. Document is in the name of the Aadhaar holder.")
    res = result(capture(text), "address_update")
    assert res.requirements[0]["category"] == "proof_of_address"
    assert validations(res, document("passport"))[0]["status"] == "unknown"


def test_agent_only_returns_retrieval_and_preserves_link_provenance():
    from agents.knowledge_based.information_retrieval.agent import InformationRetrievalAgent
    retriever = Mock()
    retriever.retrieve.return_value = result()
    pipeline = Mock()
    agent = InformationRetrievalAgent(hybrid_retriever=retriever, doc_pipeline=pipeline)
    res = agent.retrieve(RetrievalRequest(request_id="request", goal="Synthetic requirement lookup", service="document_update", domain="aadhaar"), user_documents=[document("passport")])
    pipeline.process_document.assert_not_called()
    assert res.procedure == []
    assert any(ev.metadata.get("requirement_validation", {}).get("status") == "accepted" for ev in res.evidence)


def test_accepted_candidate_selected_ahead_of_unlisted_document():
    links = RequirementDocumentLinker().link(result(), [document("aadhaar"), document("passport").model_copy(update={"document_id": "passport"})])
    assert all(link.metadata["requirement_validation"]["status"] == "accepted" for link in links.links)
    assert all(link.matched_document_id == "passport" for link in links.links)


def test_static_fallback_does_not_fabricate_source_check_or_retrieval_date():
    evidence, _, sources = get_canonical_evidence_and_requirements("address")
    assert evidence[0].retrieved_at == ""
    assert sources[0].last_checked == ""


def test_government_fetcher_verifies_tls_certificate():
    from unittest.mock import patch
    from agents.knowledge_based.information_retrieval.live_retrieval.live_fetcher import LiveGovernmentFetcher
    with patch("agents.knowledge_based.information_retrieval.live_retrieval.live_fetcher.httpx.Client") as client:
        response = client.return_value.__enter__.return_value.get.return_value
        response.status_code = 200
        response.url = FAQ_URL
        response.headers = {}
        response.text = "<html><body>" + ANSWER + "</body></html>"
        LiveGovernmentFetcher().fetch_source(capture().source)
        assert client.call_args.kwargs["verify"] is True


def test_changed_faq_structure_does_not_invent_acceptance():
    changed = ANSWER.replace("Some common documents accepted as POI only:", "Documents:")
    assert supporting_requirements("document_update", [capture(changed)]) == []
