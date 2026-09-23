"""
Document Cleaner for removing formatting artifacts while preserving source meaning.
"""
import re
import logging

logger = logging.getLogger(__name__)


class DocumentCleaner:
    """
    Cleans raw extracted text from PDFs by removing extraction artifacts and normalizing whitespace.
    """

    # Non-printable control characters excluding \n and \t
    CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    # Multiple spaces/tabs
    HORIZONTAL_WHITESPACE_REGEX = re.compile(r"[ \t]+")
    # Excessive blank lines
    MULTIPLE_NEWLINES_REGEX = re.compile(r"\n{3,}")

    def clean_text(self, raw_text: str) -> str:
        """
        Cleans raw extracted text while preserving government terms, numbers, and meaning.
        """
        if not raw_text:
            return ""

        # Remove control characters
        text = self.CONTROL_CHAR_REGEX.sub("", raw_text)

        # Normalize line-level spaces
        lines = [self.HORIZONTAL_WHITESPACE_REGEX.sub(" ", line).strip() for line in text.splitlines()]
        cleaned = "\n".join(lines)

        # Normalize multiple newlines
        cleaned = self.MULTIPLE_NEWLINES_REGEX.sub("\n\n", cleaned)

        return cleaned.strip()
