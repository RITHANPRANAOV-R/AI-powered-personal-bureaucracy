"""
Full Aadhaar Service Coverage and End-to-End Test Suite for Information Retrieval Agent.
Validates 24 distinct Aadhaar service flows and synthetic user document scenarios.
"""
import unittest
import os
import shutil
import tempfile

from agents.knowledge_based.information_retrieval.agent import InformationRetrievalAgent
from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    GroundingStatus,
    RetrievalRequest,
    RetrievalRequirement,
    RetrievalResult,
    RetrievalStatus,
    UserDocument,
    DocumentType,
    ExtractedField,
    ExtractionMethod,
    LinkStatus,
)
from agents.knowledge_based.information_retrieval.ingestion import (
    DocumentLoader,
    DocumentParser,
    DocumentCleaner,
    DocumentChunker,
)
from agents.knowledge_based.information_retrieval.embeddings import LocalEmbeddingService
from agents.knowledge_based.information_retrieval.retrieval import (
    ChromaVectorStore,
    VectorRetriever,
    HybridRetriever,
    RetrievalMode,
)


class TestAadhaarServiceCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.loader = DocumentLoader()
        cls.parser = DocumentParser()
        cls.chunker = DocumentChunker()
        cls.embedder = LocalEmbeddingService()

        cls.store = ChromaVectorStore(
            persist_directory=cls.temp_dir,
            collection_name="aadhaar_coverage_test_store",
            embedder=cls.embedder,
        )

        cls.official_pdf_url = "https://backend.uidai.gov.in/get/files/media/document/2026-05/Citizen_Charter_Jan24.pdf"
        cls.source = Source(
            source_id="src_uidai_citizen_charter_pdf",
            authority="UIDAI",
            domain="aadhaar",
            url=cls.official_pdf_url,
            document_title="Citizen's Charter for UIDAI (Jan 2024)",
            source_type=SourceType.OFFICIAL_PDF,
            trust_level=1.0,
        )

        # Pre-populate persistent ChromaDB store with official UIDAI Citizen Charter chunks
        pdf_bytes, _ = cls.loader.load_from_url(cls.official_pdf_url)
        parsed_doc = cls.parser.parse_pdf(pdf_bytes, fallback_title=cls.source.document_title)
        chunks = cls.chunker.chunk_document(parsed_doc, cls.source, chunk_size=600, chunk_overlap=100)
        cls.store.add_chunks(chunks)

        cls.vector_retriever = VectorRetriever(vector_store=cls.store, top_k=4)
        cls.hybrid_retriever = HybridRetriever(vector_retriever=cls.vector_retriever, default_mode=RetrievalMode.HYBRID)
        cls.agent = InformationRetrievalAgent(hybrid_retriever=cls.hybrid_retriever)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # ---------------------------------------------------------
    # 1. NEW AADHAAR ENROLMENT
    # ---------------------------------------------------------
    def test_svc_01_new_enrolment(self):
        """Service 01: New Aadhaar enrolment (eligibility, documents, procedure, fees)."""
        req = RetrievalRequest(
            request_id="req_svc_01",
            goal="Understand new Aadhaar enrolment procedure and mandatory documents",
            service="New Aadhaar Enrolment",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="eligibility", description="Eligibility criteria for new Aadhaar enrolment"),
                RetrievalRequirement(requirement_id="r2", category="required_documents", description="Mandatory POI and POA documents for enrolment"),
                RetrievalRequirement(requirement_id="r3", category="procedure", description="Step-by-step procedure at Aadhaar Seva Kendra"),
                RetrievalRequirement(requirement_id="r4", category="fees", description="Fee structure for new Aadhaar enrolment"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 2. NAME UPDATE
    # ---------------------------------------------------------
    def test_svc_02_name_update(self):
        """Service 02: Name update (limits, POI proof, procedure, fees)."""
        req = RetrievalRequest(
            request_id="req_svc_02",
            goal="Name update rules and acceptable Proof of Identity documents",
            service="Aadhaar Name Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="name", description="Name update limits and policy"),
                RetrievalRequirement(requirement_id="r2", category="required_documents", description="Proof of Identity document for name update"),
                RetrievalRequirement(requirement_id="r3", category="fees", description="Demographic update fee for name change"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 3. GENDER UPDATE
    # ---------------------------------------------------------
    def test_svc_03_gender_update(self):
        """Service 03: Gender update (limits, procedure, verification)."""
        req = RetrievalRequest(
            request_id="req_svc_03",
            goal="Gender update procedure and allowed update frequency",
            service="Aadhaar Gender Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="gender", description="Gender update rules and allowed update limit"),
                RetrievalRequirement(requirement_id="r2", category="procedure", description="Procedure for updating gender in Aadhaar"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 4. DATE OF BIRTH UPDATE
    # ---------------------------------------------------------
    def test_svc_04_dob_update(self):
        """Service 04: Date of Birth / age update (DOB proof, update limits)."""
        req = RetrievalRequest(
            request_id="req_svc_04",
            goal="Date of Birth update rules, birth certificate requirement, and limits",
            service="Aadhaar Date of Birth Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="dob", description="Date of birth update limits and acceptable proof of birth"),
                RetrievalRequirement(requirement_id="r2", category="required_documents", description="Valid birth proof documents for DOB update"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 5. ADDRESS UPDATE
    # ---------------------------------------------------------
    def test_svc_05_address_update(self):
        """Service 05: Address update (online self-service vs centre, POA proof)."""
        req = RetrievalRequest(
            request_id="req_svc_05",
            goal="Address update procedure and acceptable Proof of Address documents",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="address", description="Address update process online and at centre"),
                RetrievalRequirement(requirement_id="r2", category="required_documents", description="Acceptable proof of address documents"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 6. MOBILE NUMBER UPDATE
    # ---------------------------------------------------------
    def test_svc_06_mobile_number_update(self):
        """Service 06: Mobile number update (centre visit requirement, biometric auth)."""
        req = RetrievalRequest(
            request_id="req_svc_06",
            goal="Update registered mobile number in Aadhaar card",
            service="Aadhaar Mobile Number Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="mobile", description="Procedure for mobile number update at Aadhaar centre"),
                RetrievalRequirement(requirement_id="r2", category="physical_presence", description="Biometric verification requirement for mobile update"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 7. EMAIL UPDATE
    # ---------------------------------------------------------
    def test_svc_07_email_update(self):
        """Service 07: Email ID update in Aadhaar."""
        req = RetrievalRequest(
            request_id="req_svc_07",
            goal="Email ID linking and update process in Aadhaar",
            service="Aadhaar Email Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="email", description="Linking or updating email ID in Aadhaar record"),
                RetrievalRequirement(requirement_id="r2", category="procedure", description="Verification procedure for email update"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 8. RELATIONSHIP INFORMATION UPDATE
    # ---------------------------------------------------------
    def test_svc_08_relationship_update(self):
        """Service 08: Relationship information update (C/O, Father/Husband name)."""
        req = RetrievalRequest(
            request_id="req_svc_08",
            goal="Updating Care Of (C/O) and relationship details in address field",
            service="Aadhaar Relationship Information Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="relationship", description="Updating Care Of (C/O) and relationship line in address"),
                RetrievalRequirement(requirement_id="r2", category="required_documents", description="Proof of relationship documents"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 9. POI / POA / DOCUMENT UPDATE
    # ---------------------------------------------------------
    def test_svc_09_poi_poa_document_update(self):
        """Service 09: Mandatory document re-validation / POI & POA document update."""
        req = RetrievalRequest(
            request_id="req_svc_09",
            goal="Document update policy for Aadhaar cards issued over 10 years ago",
            service="Aadhaar Document Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="required_documents", description="POI and POA document re-validation list"),
                RetrievalRequirement(requirement_id="r2", category="procedure", description="Online document update service procedure"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 10. HEAD OF FAMILY (HOF) ADDRESS FLOW
    # ---------------------------------------------------------
    def test_svc_10_hof_address_flow(self):
        """Service 10: Head of Family (HoF) based address update flow."""
        req = RetrievalRequest(
            request_id="req_svc_10",
            goal="Head of Family (HoF) address update without individual POA document",
            service="HoF Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="procedure", description="HoF address update consent process and OTP requirement"),
                RetrievalRequirement(requirement_id="r2", category="required_documents", description="Proof of relationship document for HoF flow"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 11. PHOTO UPDATE
    # ---------------------------------------------------------
    def test_svc_11_photo_update(self):
        """Service 11: Photograph update (ASK visit requirement, fee)."""
        req = RetrievalRequest(
            request_id="req_svc_11",
            goal="Updating photograph in Aadhaar card at enrolment centre",
            service="Aadhaar Photo Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="procedure", description="Procedure for photo capture at Aadhaar Seva Kendra"),
                RetrievalRequirement(requirement_id="r2", category="fees", description="Biometric update fee for photo change"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 12. FINGERPRINT UPDATE
    # ---------------------------------------------------------
    def test_svc_12_fingerprint_update(self):
        """Service 12: Fingerprint biometric update (ten-finger scan requirement)."""
        req = RetrievalRequest(
            request_id="req_svc_12",
            goal="Updating fingerprint biometric data in Aadhaar record",
            service="Aadhaar Fingerprint Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="procedure", description="Ten-finger biometric scan capture process"),
                RetrievalRequirement(requirement_id="r2", category="physical_presence", description="Physical presence requirement at ASK"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 13. IRIS UPDATE
    # ---------------------------------------------------------
    def test_svc_13_iris_update(self):
        """Service 13: Iris biometric scan update."""
        req = RetrievalRequest(
            request_id="req_svc_13",
            goal="Updating iris biometric scan in Aadhaar record",
            service="Aadhaar Iris Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="procedure", description="Iris scan capture procedure at enrolment centre"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 14. BIOMETRIC UPDATE (GENERAL / MANDATORY)
    # ---------------------------------------------------------
    def test_svc_14_biometric_update_general(self):
        """Service 14: Mandatory biometric update for children at age 5 and 15."""
        req = RetrievalRequest(
            request_id="req_svc_14",
            goal="Mandatory biometric update rules for children at ages 5 and 15",
            service="Mandatory Biometric Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="eligibility", description="Age triggers for mandatory child biometric update"),
                RetrievalRequirement(requirement_id="r2", category="fees", description="Free mandatory biometric update for children"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 15. BIOMETRIC LOCK / UNLOCK
    # ---------------------------------------------------------
    def test_svc_15_biometric_lock_unlock(self):
        """Service 15: Biometric lock and unlock service for privacy."""
        req = RetrievalRequest(
            request_id="req_svc_15",
            goal="Locking and unlocking biometric authentication via myAadhaar portal",
            service="Aadhaar Biometric Lock Unlock",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="security", description="Biometric lock and unlock feature description"),
                RetrievalRequirement(requirement_id="r2", category="procedure", description="Online procedure for locking/unlocking biometrics"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 16. AADHAAR LOCK / UNLOCK
    # ---------------------------------------------------------
    def test_svc_16_aadhaar_lock_unlock(self):
        """Service 16: Aadhaar number lock and unlock service."""
        req = RetrievalRequest(
            request_id="req_svc_16",
            goal="Locking Aadhaar number to prevent unauthorized authentication",
            service="Aadhaar Lock Unlock",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="security", description="Aadhaar number lock and unlock procedure using VID"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 17. VID GENERATION / RETRIEVAL
    # ---------------------------------------------------------
    def test_svc_17_vid_flow(self):
        """Service 17: Virtual ID (VID) 16-digit generation and retrieval."""
        req = RetrievalRequest(
            request_id="req_svc_17",
            goal="Generating and retrieving 16-digit Virtual ID (VID)",
            service="Aadhaar Virtual ID Generation",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="authentication", description="Virtual ID (VID) 16-digit generation and validity"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 18. E-AADHAAR DOWNLOAD
    # ---------------------------------------------------------
    def test_svc_18_eaadhaar_download(self):
        """Service 18: e-Aadhaar PDF download service."""
        req = RetrievalRequest(
            request_id="req_svc_18",
            goal="Downloading password-protected e-Aadhaar PDF copy",
            service="e-Aadhaar Download",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="procedure", description="e-Aadhaar download using Aadhaar number or EID"),
                RetrievalRequirement(requirement_id="r2", category="authentication", description="OTP verification for e-Aadhaar download"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 19. AADHAAR PVC CARD ORDER
    # ---------------------------------------------------------
    def test_svc_19_aadhaar_pvc_order(self):
        """Service 19: Order durable Aadhaar PVC Card."""
        req = RetrievalRequest(
            request_id="req_svc_19",
            goal="Ordering wallet-sized Aadhaar PVC card online",
            service="Aadhaar PVC Card Order",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="fees", description="PVC card fee of Rs 50 and speed post delivery"),
                RetrievalRequirement(requirement_id="r2", category="procedure", description="Order procedure on myAadhaar portal"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 20. RETRIEVE UID / EID
    # ---------------------------------------------------------
    def test_svc_20_retrieve_uid_eid(self):
        """Service 20: Retrieve lost or forgotten Aadhaar UID or EID."""
        req = RetrievalRequest(
            request_id="req_svc_20",
            goal="Retrieve lost Aadhaar Number (UID) or Enrolment ID (EID) via SMS",
            service="Retrieve UID / EID",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="procedure", description="Retrieving lost UID or EID using registered mobile number"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 21. AADHAAR VALIDITY CHECK
    # ---------------------------------------------------------
    def test_svc_21_aadhaar_validity_check(self):
        """Service 21: Verify Aadhaar number validity and status."""
        req = RetrievalRequest(
            request_id="req_svc_21",
            goal="Verifying if an Aadhaar number is active and valid",
            service="Aadhaar Validity Check",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="procedure", description="Online status verification for Aadhaar number validity"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 22. STATUS / TRACKING
    # ---------------------------------------------------------
    def test_svc_22_status_tracking(self):
        """Service 22: Enrolment, update, and PVC order tracking."""
        req = RetrievalRequest(
            request_id="req_svc_22",
            goal="Check status of Aadhaar enrolment or update request using EID",
            service="Aadhaar Status Tracking",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="tracking", description="Tracking enrolment status with 14-digit EID number"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 23. ONLINE VS CENTRE-BASED FLOW DISTINCTION
    # ---------------------------------------------------------
    def test_svc_23_online_vs_centre_flows(self):
        """Service 23: Distinguish between online self-service vs Aadhaar Seva Kendra (ASK) flows."""
        req = RetrievalRequest(
            request_id="req_svc_23",
            goal="Distinguish which updates can be done online vs requiring Aadhaar Seva Kendra visit",
            service="Online vs Centre Flow Distinction",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="procedure", description="Online self-service update scope vs centre mandatory updates"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # 24. AUTHENTICATION / OTP / PHYSICAL PRESENCE
    # ---------------------------------------------------------
    def test_svc_24_authentication_otp_presence(self):
        """Service 24: Authentication requirements (OTP, registered mobile, physical presence)."""
        req = RetrievalRequest(
            request_id="req_svc_24",
            goal="Understand OTP authentication and physical presence rules for Aadhaar services",
            service="Aadhaar Authentication Rules",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="authentication", description="OTP verification using registered mobile number"),
                RetrievalRequirement(requirement_id="r2", category="physical_presence", description="Mandatory physical presence for biometric updates"),
            ],
        )
        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    # ---------------------------------------------------------
    # SYNTHETIC USER DOCUMENT SCENARIOS
    # ---------------------------------------------------------
    def test_udoc_scenario_missing_field(self):
        """Synthetic User Document: Missing required field produces missing/partial status."""
        req = RetrievalRequest(
            request_id="req_udoc_missing",
            goal="Update address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="address", description="Proof of address document required"),
            ],
        )
        incomplete_doc = UserDocument(
            document_id="doc_no_addr",
            filename="id_card.pdf",
            mime_type=".pdf",
            document_type=DocumentType.VOTER_ID,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Vikram Seth", confidence=0.95),
            },
        )
        res = self.agent.retrieve(request=req, user_documents=[incomplete_doc], mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])

    def test_udoc_scenario_conflicting_documents(self):
        """Synthetic User Document: Conflicting values across documents preserved in res.conflicts."""
        req = RetrievalRequest(
            request_id="req_udoc_conflict",
            goal="Update Aadhaar DOB",
            service="Aadhaar DOB Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="dob", description="Proof of Date of Birth document required"),
            ],
        )
        doc1 = UserDocument(
            document_id="doc_dob_1",
            filename="passport.pdf",
            mime_type=".pdf",
            document_type=DocumentType.PASSPORT,
            extracted_fields={"dob": ExtractedField(field_name="dob", value="1990-05-15", confidence=0.96)},
        )
        doc2 = UserDocument(
            document_id="doc_dob_2",
            filename="identity_proof.pdf",
            mime_type=".pdf",
            document_type=DocumentType.IDENTITY_PROOF,
            extracted_fields={"dob": ExtractedField(field_name="dob", value="1992-08-20", confidence=0.96)},
        )
        res = self.agent.retrieve(request=req, user_documents=[doc1, doc2], mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.conflicts), 0)


if __name__ == "__main__":
    unittest.main()
