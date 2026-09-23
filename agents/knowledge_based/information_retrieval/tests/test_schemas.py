"""
Unit tests for Information Retrieval Agent Pydantic schemas.
"""
import unittest
import json
from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    RetrievalRequest,
    RetrievalRequirement,
    UserDocumentInput,
    RetrievalResult,
    RetrievalStatus,
    ConflictItem,
    WarningItem,
)


class TestSchemas(unittest.TestCase):
    def test_source_serialization(self):
        source = Source(
            source_id="src_001",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/en/my-aadhaar/update-aadhaar.html",
            document_title="UIDAI Official Address Update Guidelines",
            source_type=SourceType.LIVE_WEBPAGE,
            trust_level=1.0,
        )
        data_json = source.model_dump_json()
        restored = Source.model_validate_json(data_json)
        self.assertEqual(restored.source_id, "src_001")
        self.assertEqual(restored.authority, "UIDAI")
        self.assertEqual(restored.source_type, SourceType.LIVE_WEBPAGE)

    def test_evidence_serialization(self):
        source = Source(
            source_id="src_001",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in",
        )
        evidence = Evidence(
            evidence_id="ev_001",
            claim="Fee for online address update",
            passage="Online update of address in Aadhaar costs Rs. 50.",
            source=source,
            confidence=0.98,
            relevance_score=0.95,
        )
        data_json = evidence.model_dump_json()
        restored = Evidence.model_validate_json(data_json)
        self.assertEqual(restored.evidence_id, "ev_001")
        self.assertEqual(restored.source.authority, "UIDAI")
        self.assertEqual(restored.confidence, 0.98)

    def test_synthetic_retrieval_request_serialization(self):
        req = RetrievalRequest(
            request_id="req_12345",
            goal="Update my Aadhaar address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            entities={"document": "Aadhaar", "field": "address"},
            information_needed=["eligibility", "required_documents", "fees", "procedure"],
            requirements=[
                RetrievalRequirement(
                    requirement_id="req_req_01",
                    category="fees",
                    description="What is the current fee for online Aadhaar address update?",
                    mandatory=True,
                )
            ],
            user_documents=[
                UserDocumentInput(
                    document_id="doc_voter_01",
                    document_type="voter_id",
                    file_path="/tmp/voter_card.pdf",
                    extracted_fields={"name": "John Doe", "address": "123 Main St"},
                )
            ],
        )
        json_str = req.model_dump_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["request_id"], "req_12345")
        self.assertEqual(parsed["service"], "Aadhaar Address Update")
        self.assertEqual(len(parsed["requirements"]), 1)
        self.assertEqual(len(parsed["user_documents"]), 1)

        restored_req = RetrievalRequest.model_validate_json(json_str)
        self.assertEqual(restored_req.request_id, req.request_id)

    def test_synthetic_retrieval_result_serialization(self):
        source = Source(
            source_id="src_uidai_portal",
            authority="UIDAI",
            domain="aadhaar",
            url="https://ssup.uidai.gov.in/ssup/",
            source_type=SourceType.LIVE_WEBPAGE,
        )
        evidence = Evidence(
            evidence_id="ev_fee_01",
            claim="Fee for online address update",
            passage="A non-refundable fee of Rs 50 is charged for online address update.",
            source=source,
        )
        warning = WarningItem(
            warning_id="warn_01",
            code="CENTRE_VISIT_MAY_BE_REQUIRED",
            message="If mobile number is not linked, appointment at Aadhaar Seva Kendra is required.",
        )
        result = RetrievalResult(
            result_id="res_998877",
            request_id="req_12345",
            service="Aadhaar Address Update",
            domain="aadhaar",
            retrieval_status=RetrievalStatus.SUCCESS,
            fees={"online_update_fee": 50, "currency": "INR"},
            restrictions=["Mobile number must be linked with Aadhaar for online update"],
            evidence=[evidence],
            sources=[source],
            warnings=[warning],
        )

        json_str = result.model_dump_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["result_id"], "res_998877")
        self.assertEqual(parsed["retrieval_status"], "success")
        self.assertEqual(parsed["fees"]["online_update_fee"], 50)
        self.assertEqual(len(parsed["evidence"]), 1)

        restored_result = RetrievalResult.model_validate_json(json_str)
        self.assertEqual(restored_result.result_id, result.result_id)
        self.assertEqual(restored_result.retrieval_status, RetrievalStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
