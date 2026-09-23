"""
End-to-End Integration and Failure Recovery Test Suite for Final Information Retrieval Agent.
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
    UserDocumentInput,
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


class TestFinalIRAgentIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.loader = DocumentLoader()
        cls.parser = DocumentParser()
        cls.chunker = DocumentChunker()
        cls.embedder = LocalEmbeddingService()

        cls.store = ChromaVectorStore(
            persist_directory=cls.temp_dir,
            collection_name="final_ir_agent_e2e_test",
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

        # Pre-populate ChromaDB vector store with official UIDAI Citizen Charter PDF chunks
        pdf_bytes, _ = cls.loader.load_from_url(cls.official_pdf_url)
        parsed_doc = cls.parser.parse_pdf(pdf_bytes, fallback_title=cls.source.document_title)
        chunks = cls.chunker.chunk_document(parsed_doc, cls.source, chunk_size=600, chunk_overlap=100)
        cls.store.add_chunks(chunks)

        cls.vector_retriever = VectorRetriever(vector_store=cls.store, top_k=3)
        cls.hybrid_retriever = HybridRetriever(vector_retriever=cls.vector_retriever, default_mode=RetrievalMode.HYBRID)
        cls.agent = InformationRetrievalAgent(hybrid_retriever=cls.hybrid_retriever)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_scenario_a_official_retrieval_only(self):
        """A. Official retrieval only (KNOWLEDGE_ONLY mode)."""
        req = RetrievalRequest(
            request_id="req_e2e_01",
            goal="Update Aadhaar address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="r1",
                    category="procedure",
                    description="Service delivery timelines for Aadhaar update",
                )
            ],
        )

        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)

        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)
        self.assertGreater(len(res.sources), 0)

    def test_scenario_b_official_retrieval_with_user_document(self):
        """B. Official retrieval + user document input."""
        req = RetrievalRequest(
            request_id="req_e2e_02",
            goal="Update Aadhaar address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="req_poa",
                    category="address",
                    description="Proof of address required",
                )
            ],
        )

        user_doc = UserDocument(
            document_id="doc_user_001",
            filename="my_aadhaar_card.pdf",
            mime_type=".pdf",
            document_type=DocumentType.AADHAAR,
            extracted_fields={
                "address": ExtractedField(field_name="address", value="Flat 402 MG Road Bangalore", confidence=0.95),
                "name": ExtractedField(field_name="name", value="Ritesh Kumar", confidence=0.95),
            },
        )

        res = self.agent.retrieve(request=req, user_documents=[user_doc], mode=RetrievalMode.KNOWLEDGE_ONLY)

        self.assertIn(res.retrieval_status, ["success", "partial_success"])

        # Verify cross-evidence fusion
        udoc_evidence = [ev for ev in res.evidence if ev.metadata.get("evidence_origin") == "user_document"]
        link_evidence = [ev for ev in res.evidence if ev.metadata.get("evidence_origin") == "requirement_document_link"]

        self.assertGreater(len(udoc_evidence), 0)
        self.assertGreater(len(link_evidence), 0)

    def test_scenario_c_hybrid_retrieval_with_user_document(self):
        """C. Hybrid retrieval (ChromaDB + Live HTTP) + user document."""
        req = RetrievalRequest(
            request_id="req_e2e_03",
            goal="Find Aadhaar update fees and process",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="r_fees",
                    category="fees",
                    description="Aadhaar update fees",
                )
            ],
        )

        user_doc = UserDocument(
            document_id="doc_user_002",
            filename="passport_doc.pdf",
            mime_type=".pdf",
            document_type=DocumentType.PASSPORT,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Ritesh Kumar", confidence=0.95),
            },
        )

        res = self.agent.retrieve(request=req, user_documents=[user_doc], mode=RetrievalMode.HYBRID)

        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

    def test_scenario_d_missing_user_document_optionality(self):
        """D. Missing user documents (user_documents = None) succeeds cleanly."""
        req = RetrievalRequest(
            request_id="req_e2e_04",
            goal="Check Aadhaar update requirements",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="r_proc",
                    category="procedure",
                    description="Aadhaar update procedure",
                )
            ],
        )

        res = self.agent.retrieve(request=req, user_documents=None, mode=RetrievalMode.KNOWLEDGE_ONLY)

        self.assertIn(res.retrieval_status, ["success", "partial_success"])

    def test_scenario_e_user_document_parse_failure_recovery(self):
        """E. Unrecognized/Invalid user document input handles error gracefully without failing official retrieval."""
        req = RetrievalRequest(
            request_id="req_e2e_05",
            goal="Check Aadhaar update procedure",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="r_proc",
                    category="procedure",
                    description="Aadhaar update procedure",
                )
            ],
        )

        bad_input = "non_existent_file_path_12345.xyz"

        res = self.agent.retrieve(request=req, user_documents=[bad_input], mode=RetrievalMode.KNOWLEDGE_ONLY)

        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertTrue(any("USER_DOCUMENT_PARSE_FAILED" in w.code for w in res.warnings))

    def test_scenario_g_conflicting_user_documents(self):
        """G. Conflicting user documents preserve conflict items in RetrievalResult."""
        req = RetrievalRequest(
            request_id="req_e2e_06",
            goal="Update Aadhaar address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="req_name",
                    category="identity",
                    description="Name verification",
                )
            ],
        )

        doc1 = UserDocument(
            document_id="doc_1",
            filename="doc1.pdf",
            mime_type=".pdf",
            document_type=DocumentType.AADHAAR,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Rithan Pranaov", confidence=0.95),
            },
        )
        doc2 = UserDocument(
            document_id="doc_2",
            filename="doc2.pdf",
            mime_type=".pdf",
            document_type=DocumentType.PASSPORT,
            extracted_fields={
                "name": ExtractedField(field_name="name", value="Rithan Pranav", confidence=0.95),
            },
        )

        res = self.agent.retrieve(request=req, user_documents=[doc1, doc2], mode=RetrievalMode.KNOWLEDGE_ONLY)

        self.assertGreater(len(res.conflicts), 0)

    def test_retrieval_mode_overrides(self):
        """Test all 3 retrieval modes through the top-level InformationRetrievalAgent."""
        req = RetrievalRequest(
            request_id="req_modes_test",
            goal="Check Aadhaar enrolment process",
            service="Aadhaar Enrolment",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="r_proc",
                    category="procedure",
                    description="Aadhaar enrolment procedure",
                )
            ],
        )

        # 1. KNOWLEDGE_ONLY
        res_know = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res_know.retrieval_status, ["success", "partial_success"])

        # 2. LIVE_ONLY
        res_live = self.agent.retrieve(request=req, mode=RetrievalMode.LIVE_ONLY)
        self.assertIn(res_live.retrieval_status, ["success", "partial_success", "no_evidence_found", "source_unavailable"])

        # 3. HYBRID
        res_hybrid = self.agent.retrieve(request=req, mode=RetrievalMode.HYBRID)
        self.assertIn(res_hybrid.retrieval_status, ["success", "partial_success"])

    def test_real_uidai_knowledge_base_retrieval(self):
        """REAL UIDAI Integration Test: Queries persistent ChromaDB knowledge base."""
        req = RetrievalRequest(
            request_id="req_real_uidai",
            goal="What is the delivery timeline for Aadhaar update?",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="r_sla",
                    category="procedure",
                    description="Service delivery timeline",
                )
            ],
        )

        res = self.agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)

        self.assertIn(res.retrieval_status, ["success", "partial_success"])
        self.assertGreater(len(res.evidence), 0)

        # Verify source provenance
        for ev in res.evidence:
            self.assertIsNotNone(ev.source.source_id)
            self.assertIsNotNone(ev.source.url)
            self.assertEqual(ev.source.authority, "UIDAI")


if __name__ == "__main__":
    unittest.main()
