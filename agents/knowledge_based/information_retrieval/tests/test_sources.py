"""
Unit tests for Source Registry and UIDAI Authoritative Sources.
"""
import unittest
from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry


class TestSourceRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = SourceRegistry(include_defaults=True)

    def test_registry_loading_and_default_uidai_sources(self):
        sources = self.registry.list_sources(domain="aadhaar")
        self.assertGreaterEqual(len(sources), 7)
        authorities = {s.authority for s in sources}
        self.assertIn("UIDAI", authorities)

    def test_uidai_authority_recognition(self):
        self.assertTrue(self.registry.is_authoritative("https://uidai.gov.in/en/", "aadhaar"))
        self.assertTrue(self.registry.is_authoritative("https://myaadhaar.uidai.gov.in/CheckAadhaarStatus", "aadhaar"))
        self.assertTrue(self.registry.is_authoritative("https://backend.uidai.gov.in/doc.pdf", "aadhaar"))

    def test_untrusted_source_rejection(self):
        self.assertFalse(self.registry.is_authoritative("https://fake-aadhaar-update-news.com/guide", "aadhaar"))
        self.assertFalse(self.registry.is_authoritative("https://blog.personal-finance-forum.org/aadhaar", "aadhaar"))
        self.assertFalse(self.registry.is_authoritative("https://random-third-party-portal.in", "aadhaar"))

    def test_source_metadata_retrieval(self):
        source = self.registry.get_source("src_myaadhaar_portal")
        self.assertIsNotNone(source)
        self.assertEqual(source.authority, "UIDAI")
        self.assertEqual(source.domain, "aadhaar")
        self.assertEqual(source.url, "https://myaadhaar.uidai.gov.in/")

    def test_active_inactive_handling(self):
        inactive_source = Source(
            source_id="src_legacy_page",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/legacy",
            active=False,
        )
        self.registry.register_source(inactive_source)

        active_list = self.registry.list_sources(domain="aadhaar", active_only=True)
        self.assertNotIn("src_legacy_page", [s.source_id for s in active_list])

        all_list = self.registry.list_sources(domain="aadhaar", active_only=False)
        self.assertIn("src_legacy_page", [s.source_id for s in all_list])

    def test_live_accessibility_check_of_uidai_sources(self):
        # Verify that live official portal is accessible over HTTP
        accessible = self.registry.verify_source_accessibility("src_myaadhaar_portal", timeout=10.0)
        self.assertTrue(accessible, "MyAadhaar official portal should be accessible over HTTP")


if __name__ == "__main__":
    unittest.main()
