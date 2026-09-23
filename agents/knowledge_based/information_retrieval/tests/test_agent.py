"""
Unit tests and real end-to-end integration tests for top-level InformationRetrievalAgent.
"""
import unittest
import os
import shutil
import tempfile

from agents.knowledge_based.information_retrieval.config import RetrievalConfig
from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    GroundingStatus,
    RetrievalRequest,
    RetrievalRequirement,
    RetrievalResult,
    RetrievalStatus,
)
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry
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
from agents.knowledge_based.information_retrieval.agent import InformationRetrievalAgent


class TestInformationRetrievalAgentUnit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="test_agent_orchestration",
            embedder=self.embedder,
        )
        self.vector_retriever = VectorRetriever(vector_store=self.store, top_k=2)
        self.hybrid_retriever = HybridRetriever(vector_retriever=self.vector_retriever)
        self.agent = InformationRetrievalAgent(hybrid_retriever=self.hybrid_retriever)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_null_or_invalid_request_handling(self):
        res1 = self.agent.retrieve(None)
        self.assertEqual(res1.retrieval_status, RetrievalStatus.FAILED)
        self.assertEqual(res1.warnings[0].code, "INVALID_REQUEST")

        bad_req = RetrievalRequest(request_id="", goal="No ID", service="Aadhaar Service")
        res2 = self.agent.retrieve(bad_req)
        self.assertEqual(res2.retrieval_status, RetrievalStatus.FAILED)

    def test_knowledge_only_mode_orchestration(self):
        req = RetrievalRequest(
            request_id="req_agent_k_001",
            goal="Understand Aadhaar name update eligibility",
            service="Aadhaar Name Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="r1",
                    category="eligibility",
                    description="Who is eligible for name update",
                )
            ],
        )
        res = self.agent.retrieve(req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIsNotNone(res)
        self.assertEqual(res.request_id, "req_agent_k_001")
        self.assertEqual(res.metadata["retrieval_mode"], RetrievalMode.KNOWLEDGE_ONLY.value)

    def test_downstream_result_contract_integrity(self):
        req = RetrievalRequest(
            request_id="req_agent_contract_001",
            goal="Verify contract schema fields",
            service="Aadhaar Service",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="r1",
                    category="fees",
                    description="Aadhaar PVC card fee structure",
                )
            ],
        )
        res = self.agent.retrieve(req, mode=RetrievalMode.KNOWLEDGE_ONLY)

        # Downstream Workflow Planning Agent contract assertions
        self.assertIsNotNone(res.result_id)
        self.assertIsNotNone(res.request_id)
        self.assertIsNotNone(res.service)
        self.assertIsNotNone(res.domain)
        self.assertIsNotNone(res.retrieval_status)
        self.assertIsInstance(res.evidence, list)
        self.assertIsInstance(res.sources, list)
        self.assertIsInstance(res.conflicts, list)
        self.assertIsInstance(res.warnings, list)
        self.assertIsNotNone(res.retrieval_timestamp)


class TestRealUIDAIAgentEndToEndIntegration(unittest.TestCase):
    """
    REAL End-to-End integration test through the top-level InformationRetrievalAgent.
    Calls InformationRetrievalAgent.retrieve(request) directly.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.loader = DocumentLoader()
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="uidai_agent_e2e_phase10_test",
            embedder=self.embedder,
        )
        self.vector_retriever = VectorRetriever(vector_store=self.store, top_k=3)
        self.hybrid_retriever = HybridRetriever(vector_retriever=self.vector_retriever, default_mode=RetrievalMode.HYBRID)
        self.agent = InformationRetrievalAgent(hybrid_retriever=self.hybrid_retriever)

        self.official_pdf_url = "https://backend.uidai.gov.in/get/files/media/document/2026-05/Citizen_Charter_Jan24.pdf"
        self.source = Source(
            source_id="src_uidai_citizen_charter_pdf",
            authority="UIDAI",
            domain="aadhaar",
            url=self.official_pdf_url,
            document_title="Citizen's Charter for UIDAI (Jan 2024)",
            source_type=SourceType.OFFICIAL_PDF,
            trust_level=1.0,
        )

        # Pre-populate ChromaDB persistent store with real official UIDAI Citizen Charter PDF chunks
        pdf_bytes, _ = self.loader.load_from_url(self.official_pdf_url)
        parsed_doc = self.parser.parse_pdf(pdf_bytes, fallback_title=self.source.document_title)
        chunks = self.chunker.chunk_document(parsed_doc, self.source, chunk_size=600, chunk_overlap=100)
        self.store.add_chunks(chunks)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_real_top_level_agent_retrieval(self):
        req = RetrievalRequest(
            request_id="req_e2e_agent_001",
            goal="Retrieve service delivery timelines and resident rights from official UIDAI Charter",
            service="UIDAI Citizen Charter Information",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="req_sla",
                    category="procedure",
                    description="Service delivery timelines for enrolment and update",
                ),
                RetrievalRequirement(
                    requirement_id="req_rights",
                    category="eligibility",
                    description="Resident rights under UIDAI Citizen Charter",
                ),
            ],
        )

        # Call top-level agent directly!
        result: RetrievalResult = self.agent.retrieve(req, top_k=3)

        # 1. Verification of Retrieval Status
        self.assertIn(result.retrieval_status, [RetrievalStatus.SUCCESS, RetrievalStatus.PARTIAL_SUCCESS])
        self.assertEqual(result.request_id, "req_e2e_agent_001")
        self.assertGreater(len(result.evidence), 0)
        self.assertGreater(len(result.sources), 0)

        # 2. Provenance Preservation Check
        top_ev = result.evidence[0]
        self.assertEqual(top_ev.grounding_status, GroundingStatus.VERIFIED_GROUNDED)
        self.assertGreater(top_ev.ranking_score, 0.0)
        self.assertEqual(top_ev.source.authority, "UIDAI")
        self.assertIsNotNone(top_ev.source.url)
        if top_ev.page_number is not None:
            self.assertGreaterEqual(top_ev.page_number, 1)

        # 3. Verify Deterministic Sorting
        scores = [ev.ranking_score for ev in result.evidence]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
