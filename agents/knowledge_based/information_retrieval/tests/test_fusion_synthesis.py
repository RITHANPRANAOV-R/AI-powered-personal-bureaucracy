"""
Unit tests and realistic synthetic Aadhaar scenario tests for Phase 13 Evidence Fusion & Cross-Evidence Synthesis.
"""
import unittest

from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    GroundingStatus,
    UserDocument,
    DocumentType,
    ExtractionMethod,
    ExtractedField,
    LinkingResult,
    RequirementDocumentLink,
    LinkStatus,
)
from agents.knowledge_based.information_retrieval.retrieval import (
    EvidenceFusionEngine,
    EvidenceOrigin,
    FreshnessType,
    CoverageStatus,
    convert_user_document_to_evidence,
    convert_linking_result_to_evidence,
)


class TestEvidenceFusionSynthesisUnit(unittest.TestCase):
    def setUp(self):
        self.fusion_engine = EvidenceFusionEngine()

        self.official_source = Source(
            source_id="src_uidai_portal",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/en/",
            document_title="UIDAI Official Portal",
            trust_level=1.0,
        )

        self.stored_ev = Evidence(
            evidence_id="ev_stored_001",
            claim="Official Address Update Procedure",
            passage="A valid Proof of Address document is mandatory for updating Aadhaar address.",
            source=self.official_source,
            ranking_score=0.88,
            grounding_status=GroundingStatus.VERIFIED_GROUNDED,
            metadata={"category": "address", "requirement_id": "req_address_01"},
        )

        self.live_ev = Evidence(
            evidence_id="ev_live_001",
            claim="Live Update Fee Structure",
            passage="Aadhaar demography update fee is Rs 50 at official centres.",
            source=self.official_source,
            ranking_score=0.92,
            grounding_status=GroundingStatus.VERIFIED_GROUNDED,
            metadata={"category": "fees", "requirement_id": "req_fees_01"},
        )

        self.user_doc = UserDocument(
            document_id="doc_udoc_001",
            filename="my_aadhaar.pdf",
            mime_type=".pdf",
            document_type=DocumentType.AADHAAR,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Ritesh Kumar", confidence=0.95),
                "address": ExtractedField(field_name="address", value="Flat 101 MG Road Bangalore", confidence=0.94),
            },
        )

        self.linking_result = LinkingResult(
            linking_id="link_res_001",
            request_id="req_session_001",
            links=[
                RequirementDocumentLink(
                    link_id="link_req_address_01",
                    requirement_id="req_address_01",
                    requirement_category="address",
                    requirement_description="Proof of Address document required",
                    status=LinkStatus.CANDIDATE_MATCH,
                    matched_document_id="doc_udoc_001",
                    matched_document_type="aadhaar",
                    matched_fields=[{"field_name": "address", "value": "Flat 101 MG Road Bangalore", "confidence": 0.94}],
                    matching_reasons=["Aadhaar document matches address requirement"],
                    confidence=0.94,
                )
            ],
        )

    def test_authority_boundary_and_origin_tagging(self):
        fused_ev, sources, conflicts = self.fusion_engine.fuse_evidence(
            knowledge_evidence=[self.stored_ev],
            live_evidence=[self.live_ev],
            user_documents=[self.user_doc],
            linking_result=self.linking_result,
        )

        # Check total fused items
        self.assertGreaterEqual(len(fused_ev), 4)

        # Verify origins
        origins = [ev.metadata.get("evidence_origin") for ev in fused_ev]
        self.assertIn(EvidenceOrigin.OFFICIAL_STORED.value, origins)
        self.assertIn(EvidenceOrigin.OFFICIAL_LIVE.value, origins)
        self.assertIn(EvidenceOrigin.USER_DOCUMENT.value, origins)
        self.assertIn(EvidenceOrigin.REQUIREMENT_DOCUMENT_LINK.value, origins)

        # Verify Authority Boundary
        udoc_ev = next(ev for ev in fused_ev if ev.metadata.get("evidence_origin") == EvidenceOrigin.USER_DOCUMENT.value)
        self.assertEqual(udoc_ev.source.authority, "User Document Upload")
        self.assertEqual(udoc_ev.grounding_status, GroundingStatus.UNVERIFIED)

        official_ev = next(ev for ev in fused_ev if ev.metadata.get("evidence_origin") == EvidenceOrigin.OFFICIAL_STORED.value)
        self.assertEqual(official_ev.source.authority, "UIDAI")
        self.assertEqual(official_ev.grounding_status, GroundingStatus.VERIFIED_GROUNDED)

    def test_requirement_coverage_mapping(self):
        fused_ev, sources, conflicts = self.fusion_engine.fuse_evidence(
            knowledge_evidence=[self.stored_ev],
            live_evidence=[],
            user_documents=[self.user_doc],
            linking_result=self.linking_result,
        )

        stored_item = next(ev for ev in fused_ev if ev.evidence_id == "ev_stored_001")
        self.assertEqual(stored_item.metadata.get("coverage_status"), CoverageStatus.SUPPORTED_BY_USER_EVIDENCE.value)

    def test_synthetic_aadhaar_fusion_scenario(self):
        """
        REALISTIC SYNTHETIC AADHAAR SCENARIO:
        Fuses official requirement, official RAG evidence, user document, requirement link,
        verifying complete unified provenance without illegal legal claims.
        """
        fused_ev, sources, conflicts = self.fusion_engine.fuse_evidence(
            knowledge_evidence=[self.stored_ev],
            live_evidence=[self.live_ev],
            user_documents=[self.user_doc],
            linking_result=self.linking_result,
        )

        # 1. Assert full evidence spectrum present
        self.assertTrue(any(ev.metadata.get("field_name") == "address" for ev in fused_ev))
        self.assertTrue(any(ev.metadata.get("link_id") == "link_req_address_01" for ev in fused_ev))

        # 2. Verify neutral claim/passage wording
        for ev in fused_ev:
            self.assertNotIn("legally valid", ev.passage.lower())
            self.assertNotIn("citizen is eligible", ev.passage.lower())


if __name__ == "__main__":
    unittest.main()
