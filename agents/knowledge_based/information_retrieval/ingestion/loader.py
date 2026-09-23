"""
Document Loader for official government PDFs and documents.
"""
import os
import logging
from typing import Tuple, Dict, Any, Optional
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)


class DocumentLoadingError(Exception):
    """Exception raised when document loading fails."""
    pass


class DocumentLoader:
    """
    Loads official government PDF files from HTTP URLs or local disk paths.
    """

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def load_from_url(self, url: str) -> Tuple[bytes, Dict[str, Any]]:
        """
        Fetches official document bytes over HTTP(S).
        Returns (pdf_bytes, metadata_dict).
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/pdf,*/*",
        }

        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()

                content = response.content
                if not self.is_pdf_content(content):
                    raise DocumentLoadingError(f"URL '{url}' did not return valid PDF content (missing %PDF header)")

                metadata = {
                    "document_url": str(response.url),
                    "content_type": response.headers.get("Content-Type", "application/pdf"),
                    "content_length": len(content),
                    "last_modified": response.headers.get("Last-Modified"),
                    "etag": response.headers.get("ETag"),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
                return content, metadata

        except httpx.HTTPError as e:
            raise DocumentLoadingError(f"HTTP error fetching PDF from '{url}': {e}")
        except Exception as e:
            if isinstance(e, DocumentLoadingError):
                raise
            raise DocumentLoadingError(f"Failed to load PDF from '{url}': {e}")

    def load_from_file(self, file_path: str) -> Tuple[bytes, Dict[str, Any]]:
        """
        Loads document bytes from local file system path.
        """
        if not os.path.exists(file_path):
            raise DocumentLoadingError(f"File not found: '{file_path}'")

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            if not self.is_pdf_content(content):
                raise DocumentLoadingError(f"File '{file_path}' is not a valid PDF file (missing %PDF header)")

            stat = os.stat(file_path)
            metadata = {
                "file_path": file_path,
                "content_length": len(content),
                "file_modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
            return content, metadata
        except Exception as e:
            if isinstance(e, DocumentLoadingError):
                raise
            raise DocumentLoadingError(f"Error reading local file '{file_path}': {e}")

    @staticmethod
    def is_pdf_content(content: bytes) -> bool:
        """Checks if byte content starts with PDF magic header bytes (%PDF-)."""
        if not content or len(content) < 5:
            return False
        return content.startswith(b"%PDF-")
