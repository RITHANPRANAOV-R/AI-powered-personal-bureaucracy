"""
Unit tests and realistic Aadhaar scenario tests for RequirementDocumentLinker.
"""
import unittest
import os
import shutil
import tempfile

from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    GroundingStatus,
    RetrievalResult,
    RetrievalStatus,
    UserDocument,
    DocumentType,
    ExtractionMethod,
    OCRStatus,
    ExtractedField,
    LinkStatus,
    RequirementDocumentLink,
    LinkingResult,
)
from agents.knowledge_based.information_retrieval.retrieval import RequirementDocumentLinker


class TestRequirementDocumentLinkerUnit(unittest.TestCase):
    def setUp(self):
        self.linker = RequirementDocumentLinker()
        self.source = Source(
            source_id="src_uidai_portal",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/en/",
            document_title="UIDAI Official Portal",
        )
        self.evidence = Evidence(
            evidence_id="ev_addr_001",
            claim="Proof of Address Requirement",
            passage="A valid Proof of Address (POA) document is mandatory for Aadhaar address update.",
            source=self.source,
            metadata={"category": "address"},
        )
        self.retrieval_result = RetrievalResult(
            result_id="res_001",
            request_id="req_001",
            service="Aadhaar Address Update",
            domain="aadhaar",
            retrieval_status=RetrievalStatus.SUCCESS,
            requirements=[
                {
                    "requirement_id": "r_address",
                    "category": "address",
                    "description": "Proof of Address document required",
                },
                {
                    "requirement_id": "r_identity",
                    "category": "identity",
                    "description": "Identity proof document required",
                },
            ],
            evidence=[self.evidence],
        )

    def test_scenario_a_proof_of_address_candidate_match(self):
        # Scenario A: Requirement proof of address + Synthetic Aadhaar with address
        doc = UserDocument(
            document_id="doc_aadhaar_001",
            filename="aadhaar_card.pdf",
            mime_type=".pdf",
            document_type=DocumentType.AADHAAR,
            classification_confidence=0.9,
            extraction_method=ExtractionMethod.DIRECT_TEXT_PDF,
            extracted_fields={
                "address": ExtractedField(field_name="address", value="Flat 402 MG Road Bangalore", confidence=0.95),
                "name": ExtractedField(field_name="name", value="Ramesh Kumar", confidence=0.95),
            },
        )

        res = self.linker.link(self.retrieval_result, [doc])

        self.assertEqual(len(res.links), 2)
        addr_link = next(l for l in res.links if l.requirement_id == "r_address")
        self.assertEqual(addr_link.status, LinkStatus.CANDIDATE_MATCH)
        self.assertEqual(addr_link.matched_document_id, "doc_aadhaar_001")
        self.assertIn("ev_addr_001", addr_link.official_evidence_ids)

    def test_scenario_b_missing_document_gap(self):
        # Scenario B: Requirement proof of address + Synthetic PAN only (PAN doesn't prove address)
        pan_doc = UserDocument(
            document_id="doc_pan_001",
            filename="pan_card.png",
            mime_type=".png",
            document_type=DocumentType.PAN,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Ramesh Kumar", confidence=0.95),
                "pan_number": ExtractedField(field_name="pan_number", value="ABXXX1234C", confidence=0.95),
            },
        )

        res = self.linker.link(self.retrieval_result, [pan_doc])

        addr_link = next(l for l in res.links if l.requirement_id == "r_address")
        self.assertEqual(addr_link.status, LinkStatus.MISSING_DOCUMENT)
        self.assertIn("r_address", res.uncovered_requirements)

    def test_scenario_d_partial_match_missing_field(self):
        # Scenario D: Aadhaar uploaded but address field extraction missing
        doc_no_addr = UserDocument(
            document_id="doc_aadhaar_no_addr",
            filename="aadhaar_no_addr.pdf",
            mime_type=".pdf",
            document_type=DocumentType.AADHAAR,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Ramesh Kumar", confidence=0.95),
                # Address missing!
            },
        )

        res = self.linker.link(self.retrieval_result, [doc_no_addr])

        addr_link = next(l for l in res.links if l.requirement_id == "r_address")
        self.assertEqual(addr_link.status, LinkStatus.PARTIAL_MATCH)
        self.assertIn("address", addr_link.missing_fields)

    def test_scenario_e_inter_document_field_conflict(self):
        # Scenario E: Document A name vs Document B name conflict
        doc1 = UserDocument(
            document_id="doc_1",
            filename="doc1.pdf",
            mime_type=".pdf",
            document_type=DocumentType.AADHAAR,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Rithan Pranaov", confidence=0.95),
                "address": ExtractedField(field_name="address", value="Addr 1", confidence=0.90),
            },
        )
        doc2 = UserDocument(
            document_id="doc_2",
            filename="doc2.pdf",
            mime_type=".pdf",
            document_type=DocumentType.PASSPORT,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Rithan Pranav", confidence=0.95),
                "address": ExtractedField(field_name="address", value="Addr 1", confidence=0.90),
            },
        )

        res = self.linker.link(self.retrieval_result, [doc1, doc2])

        self.assertEqual(len(res.conflicts), 1)
        conflict = res.conflicts[0]
        self.assertEqual(conflict["field_name"], "name")
        self.assertEqual(len(conflict["competing_records"]), 2)


if __name__ == "__main__":
    unittest.main()
