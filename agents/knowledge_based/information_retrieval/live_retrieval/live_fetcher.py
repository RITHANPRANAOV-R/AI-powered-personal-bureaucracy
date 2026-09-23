"""
Live Government Web Fetcher module.
Fetches, parses, validates, and extracts text content from authoritative government sources.
"""
import logging
import time
from enum import Enum
from typing import Optional, Union, Tuple
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
import httpx
from bs4 import BeautifulSoup

from agents.knowledge_based.information_retrieval.schemas.source import Source
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry

logger = logging.getLogger(__name__)


class LiveRetrievalStatus(str, Enum):
    """Execution status for live government retrieval."""
    SUCCESS = "success"
    UNAUTHORIZED_SOURCE = "unauthorized_source"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    AUTH_REQUIRED = "auth_required"
    BLOCKED_OR_WAF = "blocked_or_waf"
    JS_SHELL_DETECTED = "js_shell_detected"
    EMPTY_OR_UNUSABLE_CONTENT = "empty_or_unusable_content"
    SOURCE_UNAVAILABLE = "source_unavailable"


class LiveRetrievalResult(BaseModel):
    """
    Structured outcome of a live government HTTP retrieval attempt.
    """
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    source_id: str = Field(description="Associated source ID")
    authority: str = Field(description="Governing authority e.g. UIDAI")
    url: str = Field(description="Target URL attempted")
    redirected_url: Optional[str] = Field(default=None, description="Final URL if redirected")
    status: LiveRetrievalStatus = Field(description="Retrieval status classification")
    http_status_code: Optional[int] = Field(default=None, description="HTTP status code returned")
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 retrieval timestamp"
    )
    page_title: Optional[str] = Field(default=None, description="Extracted HTML title")
    extracted_text: Optional[str] = Field(default=None, description="Cleaned, extracted text content")
    content_type: Optional[str] = Field(default=None, description="HTTP Response Content-Type")
    content_length: Optional[int] = Field(default=None, description="Content length in bytes")
    last_modified: Optional[str] = Field(default=None, description="Source Last-Modified header if present")
    etag: Optional[str] = Field(default=None, description="Source ETag header if present")
    is_usable_content: bool = Field(default=False, description="Whether extracted content is valid government text")
    error_message: Optional[str] = Field(default=None, description="Details of error if failed")


class LiveGovernmentFetcher:
    """
    Fetches and parses live government web pages safely with provenance preservation.
    """

    UNUSABLE_JS_SIGNATURES = [
        "you need to enable javascript to run this app",
        "javascript is required",
        "please enable javascript",
    ]

    BLOCKED_WAF_SIGNATURES = [
        "access denied",
        "attention required! | cloudflare",
        "security check",
        "captcha",
        "web application firewall",
        "request blocked",
    ]

    def __init__(self, source_registry: Optional[SourceRegistry] = None):
        self.registry = source_registry or SourceRegistry(include_defaults=True)

    def fetch_source(
        self,
        source_or_id: Union[Source, str],
        timeout: float = 15.0,
        retries: int = 1,
    ) -> LiveRetrievalResult:
        """
        Fetches an authoritative government source URL live over HTTP.
        """
        if isinstance(source_or_id, str):
            source = self.registry.get_source(source_or_id)
            if not source:
                return LiveRetrievalResult(
                    source_id=source_or_id,
                    authority="UNKNOWN",
                    url="",
                    status=LiveRetrievalStatus.SOURCE_UNAVAILABLE,
                    error_message=f"Source ID '{source_or_id}' not found in registry",
                )
        else:
            source = source_or_id

        # Verify source authority via SourceRegistry
        if not source.url or not self.registry.is_authoritative(source.url, source.domain):
            return LiveRetrievalResult(
                source_id=source.source_id,
                authority=source.authority,
                url=source.url or "",
                status=LiveRetrievalStatus.UNAUTHORIZED_SOURCE,
                error_message=f"URL '{source.url}' is not an authoritative domain for '{source.domain}'",
            )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        last_exception = None

        for attempt in range(retries + 1):
            try:
                with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
                    response = client.get(source.url)
                    return self._process_response(source, response)
            except httpx.TimeoutException as e:
                logger.warning(f"Timeout fetching {source.url} (attempt {attempt+1}/{retries+1}): {e}")
                last_exception = e
            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP status error for {source.url}: {e}")
                return self._handle_http_error(source, e.response)
            except Exception as e:
                logger.warning(f"Request error fetching {source.url} (attempt {attempt+1}/{retries+1}): {e}")
                last_exception = e

            if attempt < retries:
                time.sleep(1.0)

        # Timeout / Retry Exhausted
        if isinstance(last_exception, httpx.TimeoutException):
            return LiveRetrievalResult(
                source_id=source.source_id,
                authority=source.authority,
                url=source.url,
                status=LiveRetrievalStatus.TIMEOUT,
                error_message=f"Request timed out after {timeout} seconds",
            )
        else:
            return LiveRetrievalResult(
                source_id=source.source_id,
                authority=source.authority,
                url=source.url,
                status=LiveRetrievalStatus.HTTP_ERROR,
                error_message=f"Failed to connect to source: {str(last_exception)}",
            )

    def _process_response(self, source: Source, response: httpx.Response) -> LiveRetrievalResult:
        """Process HTTP 200/Redirect responses and extract structured text."""
        status_code = response.status_code
        redirected_url = str(response.url) if str(response.url) != source.url else None

        if status_code in (401, 403):
            return LiveRetrievalResult(
                source_id=source.source_id,
                authority=source.authority,
                url=source.url,
                redirected_url=redirected_url,
                status=LiveRetrievalStatus.AUTH_REQUIRED if status_code == 401 else LiveRetrievalStatus.BLOCKED_OR_WAF,
                http_status_code=status_code,
                error_message=f"Access restricted by government portal (HTTP {status_code})",
            )
        elif status_code >= 400:
            return LiveRetrievalResult(
                source_id=source.source_id,
                authority=source.authority,
                url=source.url,
                redirected_url=redirected_url,
                status=LiveRetrievalStatus.HTTP_ERROR,
                http_status_code=status_code,
                error_message=f"HTTP Error {status_code}",
            )

        content_type = response.headers.get("Content-Type", "")
        last_modified = response.headers.get("Last-Modified")
        etag = response.headers.get("ETag")

        # HTML Content Parsing
        title, text, is_usable, status = self._extract_content_and_title(response.text)

        return LiveRetrievalResult(
            source_id=source.source_id,
            authority=source.authority,
            url=source.url,
            redirected_url=redirected_url,
            status=status,
            http_status_code=status_code,
            page_title=title,
            extracted_text=text,
            content_type=content_type,
            content_length=len(response.content),
            last_modified=last_modified,
            etag=etag,
            is_usable_content=is_usable,
        )

    def _handle_http_error(self, source: Source, response: httpx.Response) -> LiveRetrievalResult:
        """Categorize HTTP error status codes."""
        code = response.status_code
        if code in (401, 403):
            status = LiveRetrievalStatus.AUTH_REQUIRED if code == 401 else LiveRetrievalStatus.BLOCKED_OR_WAF
        else:
            status = LiveRetrievalStatus.HTTP_ERROR

        return LiveRetrievalResult(
            source_id=source.source_id,
            authority=source.authority,
            url=source.url,
            status=status,
            http_status_code=code,
            error_message=f"HTTP Server returned status code {code}",
        )

    def _extract_content_and_title(self, html_content: str) -> Tuple[Optional[str], Optional[str], bool, LiveRetrievalStatus]:
        """
        Parses HTML, removes scripts/styles/navs, extracts clean text, and validates usability.
        """
        if not html_content or not html_content.strip():
            return None, None, False, LiveRetrievalStatus.EMPTY_OR_UNUSABLE_CONTENT

        raw_lower = html_content.lower()

        # Check for WAF / Security blocks in raw HTML or title
        for signature in self.BLOCKED_WAF_SIGNATURES:
            if signature in raw_lower:
                return None, None, False, LiveRetrievalStatus.BLOCKED_OR_WAF

        # Check for JS SPA Shell signatures in raw HTML before element stripping
        for signature in self.UNUSABLE_JS_SIGNATURES:
            if signature in raw_lower:
                return None, None, False, LiveRetrievalStatus.JS_SHELL_DETECTED

        try:
            soup = BeautifulSoup(html_content, "html.parser")

            title = soup.title.string.strip() if soup.title and soup.title.string else None

            # Remove unwanted structural tags
            for elem in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                elem.decompose()

            extracted_text = " ".join(soup.get_text().split())

            if len(extracted_text) < 100:
                return title, extracted_text, False, LiveRetrievalStatus.EMPTY_OR_UNUSABLE_CONTENT

            return title, extracted_text, True, LiveRetrievalStatus.SUCCESS

        except Exception as e:
            logger.error(f"HTML parsing failed: {e}")
            return None, None, False, LiveRetrievalStatus.EMPTY_OR_UNUSABLE_CONTENT
