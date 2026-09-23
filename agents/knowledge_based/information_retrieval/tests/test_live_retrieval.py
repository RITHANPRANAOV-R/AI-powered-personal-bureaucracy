"""
Unit tests and real live integration tests for LiveGovernmentFetcher.
"""
import unittest
from unittest.mock import MagicMock, patch
import httpx

from agents.knowledge_based.information_retrieval.schemas.source import Source
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry
from agents.knowledge_based.information_retrieval.live_retrieval.live_fetcher import (
    LiveGovernmentFetcher,
    LiveRetrievalResult,
    LiveRetrievalStatus,
)


class TestLiveGovernmentFetcherMocked(unittest.TestCase):
    def setUp(self):
        self.registry = SourceRegistry(include_defaults=True)
        self.fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        self.valid_source = Source(
            source_id="src_uidai_test",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/en/test-page.html",
        )

    def test_unauthorized_source_rejection(self):
        untrusted_source = Source(
            source_id="src_fake",
            authority="UNTRUSTED",
            domain="aadhaar",
            url="https://fake-government-portal.com/page",
        )
        res = self.fetcher.fetch_source(untrusted_source)
        self.assertEqual(res.status, LiveRetrievalStatus.UNAUTHORIZED_SOURCE)
        self.assertFalse(res.is_usable_content)

    @patch.object(httpx.Client, "get")
    def test_successful_http_retrieval_and_parsing(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://uidai.gov.in/en/test-page.html"
        mock_response.headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Last-Modified": "Wed, 15 Jan 2026 10:00:00 GMT",
        }
        mock_response.text = """
        <html>
            <head><title>Official UIDAI Guidelines</title></head>
            <body>
                <script>console.log("ignore me");</script>
                <h1>Aadhaar Address Update Rules</h1>
                <p>This is official authoritative text for updating address in Aadhaar card. Minimum length check requires sufficient text.</p>
                <footer>Footer links to ignore</footer>
            </body>
        </html>
        """
        mock_response.content = mock_response.text.encode("utf-8")
        mock_get.return_value = mock_response

        res = self.fetcher.fetch_source(self.valid_source)
        self.assertEqual(res.status, LiveRetrievalStatus.SUCCESS)
        self.assertEqual(res.http_status_code, 200)
        self.assertEqual(res.page_title, "Official UIDAI Guidelines")
        self.assertIn("Aadhaar Address Update Rules", res.extracted_text)
        self.assertNotIn("console.log", res.extracted_text)
        self.assertTrue(res.is_usable_content)
        self.assertEqual(res.last_modified, "Wed, 15 Jan 2026 10:00:00 GMT")

    @patch.object(httpx.Client, "get")
    def test_js_shell_detection(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://myaadhaar.uidai.gov.in/"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = """
        <html>
            <head><title>myAadhaar Portal</title></head>
            <body>
                <noscript>You need to enable JavaScript to run this app.</noscript>
                <div id="root"></div>
            </body>
        </html>
        """
        mock_response.content = mock_response.text.encode("utf-8")
        mock_get.return_value = mock_response

        source = self.registry.get_source("src_myaadhaar_portal")
        res = self.fetcher.fetch_source(source)
        self.assertEqual(res.status, LiveRetrievalStatus.JS_SHELL_DETECTED)
        self.assertFalse(res.is_usable_content)

    @patch.object(httpx.Client, "get")
    def test_waf_blocked_detection(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.url = "https://uidai.gov.in/en/test"
        mock_response.headers = {}
        mock_response.text = "<html><head><title>Access Denied</title></head><body>Attention Required! | Cloudflare</body></html>"
        mock_response.content = mock_response.text.encode("utf-8")
        mock_get.return_value = mock_response

        res = self.fetcher.fetch_source(self.valid_source)
        self.assertEqual(res.status, LiveRetrievalStatus.BLOCKED_OR_WAF)
        self.assertFalse(res.is_usable_content)

    @patch.object(httpx.Client, "get")
    def test_timeout_handling(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("Connection timed out")
        res = self.fetcher.fetch_source(self.valid_source, retries=0)
        self.assertEqual(res.status, LiveRetrievalStatus.TIMEOUT)
        self.assertIn("timed out", res.error_message.lower())
        self.assertFalse(res.is_usable_content)

    @patch.object(httpx.Client, "get")
    def test_redirect_handling(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://uidai.gov.in/en/my-aadhaar/about-aadhaar.html"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = "<html><head><title>Redirected Page</title></head><body>" + ("Official text content " * 20) + "</body></html>"
        mock_response.content = mock_response.text.encode("utf-8")
        mock_get.return_value = mock_response

        res = self.fetcher.fetch_source(self.valid_source)
        self.assertEqual(res.status, LiveRetrievalStatus.SUCCESS)
        self.assertEqual(res.redirected_url, "https://uidai.gov.in/en/my-aadhaar/about-aadhaar.html")


class TestLiveGovernmentFetcherRealIntegration(unittest.TestCase):
    """
    Real Integration Tests executing live HTTP GET requests against official UIDAI sources.
    """
    def setUp(self):
        self.registry = SourceRegistry(include_defaults=True)
        self.fetcher = LiveGovernmentFetcher(source_registry=self.registry)

    def test_real_live_retrieval_uidai_portal(self):
        source = self.registry.get_source("src_uidai_portal_en")
        self.assertIsNotNone(source)

        res = self.fetcher.fetch_source(source, timeout=15.0, retries=1)
        self.assertEqual(res.source_id, "src_uidai_portal_en")
        self.assertEqual(res.http_status_code, 200)
        self.assertEqual(res.status, LiveRetrievalStatus.SUCCESS)
        self.assertTrue(res.is_usable_content)
        self.assertIsNotNone(res.page_title)
        self.assertTrue(
            "Unique Identification Authority of India" in res.page_title or "UIDAI" in res.page_title,
            f"Expected official title, got: {res.page_title}"
        )
        self.assertGreater(len(res.extracted_text), 200)

    def test_real_live_retrieval_myaadhaar_portal(self):
        source = self.registry.get_source("src_myaadhaar_portal")
        self.assertIsNotNone(source)

        res = self.fetcher.fetch_source(source, timeout=15.0, retries=1)
        self.assertEqual(res.source_id, "src_myaadhaar_portal")
        self.assertEqual(res.http_status_code, 200)
        # myAadhaar portal is a React SPA; JS shell detection or direct fetch is valid
        self.assertIn(res.status, [LiveRetrievalStatus.SUCCESS, LiveRetrievalStatus.JS_SHELL_DETECTED])


if __name__ == "__main__":
    unittest.main()
