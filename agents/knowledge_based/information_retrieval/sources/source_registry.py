"""
Authoritative Source Registry for Information Retrieval Agent.
Manages trusted government sources and validates domain authority.
"""
import logging
from typing import Dict, List, Optional
from urllib.parse import urlparse
import httpx

from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType

logger = logging.getLogger(__name__)


class SourceRegistry:
    """
    Registry managing authoritative government sources.
    Designed generically to support Aadhaar and future government domains.
    """

    TRUSTED_AUTHORITY_DOMAINS: Dict[str, List[str]] = {
        "aadhaar": [
            "uidai.gov.in",
            "myaadhaar.uidai.gov.in",
            "backend.uidai.gov.in",
            "appointments.uidai.gov.in",
            "myaadhaarbeta.uidai.gov.in",
        ]
    }

    def __init__(self, include_defaults: bool = True):
        self._sources: Dict[str, Source] = {}
        if include_defaults:
            self._load_default_uidai_sources()

    def register_source(self, source: Source) -> None:
        """Register a new source in the registry."""
        if not self.is_authoritative(source.url, source.domain):
            logger.warning(
                f"Registering non-standard source {source.source_id} for domain {source.domain}: {source.url}"
            )
        self._sources[source.source_id] = source

    def get_source(self, source_id: str) -> Optional[Source]:
        """Retrieve a registered source by ID."""
        return self._sources.get(source_id)

    def list_sources(
        self,
        domain: Optional[str] = None,
        authority: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Source]:
        """List registered sources matching optional domain/authority filters."""
        results = []
        for source in self._sources.values():
            if active_only and not source.active:
                continue
            if domain and source.domain.lower() != domain.lower():
                continue
            if authority and source.authority.lower() != authority.lower():
                continue
            results.append(source)
        return results

    def is_authoritative(self, url: Optional[str], domain: str) -> bool:
        """
        Validates whether a URL belongs to a trusted government domain authority.
        Rejects blogs, news sites, forums, and unverified third-party domains.
        """
        if not url:
            return False

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return False

            trusted_domains = self.TRUSTED_AUTHORITY_DOMAINS.get(domain.lower(), [])
            for trusted in trusted_domains:
                if hostname == trusted or hostname.endswith("." + trusted):
                    return True
            return False
        except Exception as e:
            logger.error(f"Error parsing URL {url}: {e}")
            return False

    def verify_source_accessibility(self, source_id: str, timeout: float = 10.0) -> bool:
        """
        Performs a live HTTP GET request to verify source availability.
        """
        source = self.get_source(source_id)
        if not source or not source.url:
            return False

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
                response = client.get(source.url)
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Accessibility check failed for {source.source_id} ({source.url}): {e}")
            return False

    def _load_default_uidai_sources(self) -> None:
        """Pre-populate verified official UIDAI sources."""
        uidai_sources = [
            Source(
                source_id="src_uidai_portal_en",
                authority="UIDAI",
                domain="aadhaar",
                url="https://uidai.gov.in/en/",
                document_title="UIDAI Official English Portal",
                source_type=SourceType.LIVE_WEBPAGE,
                trust_level=1.0,
                freshness_policy="live",
            ),
            Source(
                source_id="src_myaadhaar_portal",
                authority="UIDAI",
                domain="aadhaar",
                url="https://myaadhaar.uidai.gov.in/",
                document_title="MyAadhaar Resident Services Portal",
                source_type=SourceType.LIVE_WEBPAGE,
                trust_level=1.0,
                freshness_policy="live",
            ),
            Source(
                source_id="src_uidai_check_status",
                authority="UIDAI",
                domain="aadhaar",
                url="https://myaadhaar.uidai.gov.in/CheckAadhaarStatus",
                document_title="Aadhaar Enrolment & Update Status Tracking",
                source_type=SourceType.LIVE_WEBPAGE,
                trust_level=1.0,
                freshness_policy="live",
            ),
            Source(
                source_id="src_uidai_download",
                authority="UIDAI",
                domain="aadhaar",
                url="https://myaadhaar.uidai.gov.in/genricDownloadAadhaar",
                document_title="e-Aadhaar Download Service",
                source_type=SourceType.LIVE_WEBPAGE,
                trust_level=1.0,
                freshness_policy="live",
            ),
            Source(
                source_id="src_uidai_retrieve_eid",
                authority="UIDAI",
                domain="aadhaar",
                url="https://myaadhaar.uidai.gov.in/retrieve-eid-uid",
                document_title="Retrieve Lost EID/UID Service",
                source_type=SourceType.LIVE_WEBPAGE,
                trust_level=1.0,
                freshness_policy="live",
            ),
            Source(
                source_id="src_uidai_pvc",
                authority="UIDAI",
                domain="aadhaar",
                url="https://myaadhaar.uidai.gov.in/genricPVC",
                document_title="Order Aadhaar PVC Card Service",
                source_type=SourceType.LIVE_WEBPAGE,
                trust_level=1.0,
                freshness_policy="live",
            ),
            Source(
                source_id="src_uidai_validity",
                authority="UIDAI",
                domain="aadhaar",
                url="https://myaadhaar.uidai.gov.in/check-aadhaar-validity",
                document_title="Check Aadhaar Validity Service",
                source_type=SourceType.LIVE_WEBPAGE,
                trust_level=1.0,
                freshness_policy="live",
            ),
        ]

        for source in uidai_sources:
            self.register_source(source)
