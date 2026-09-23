"""
Document Classifier and Field Extractor for User Document Understanding.
Extracted field values are preserved with confidence scores, page provenance, and privacy-safe logging.
"""
import re
import logging
from typing import Tuple, Dict, Any, Optional
from agents.knowledge_based.information_retrieval.schemas.user_document import (
    DocumentType,
    ExtractedField,
)

logger = logging.getLogger(__name__)


class DocumentClassifier:
    """
    Classifies raw extracted text into standard document categories.
    """

    KEYWORD_MAP = {
        DocumentType.AADHAAR: [
            r"unique identification authority", r"aadhaar", r"uidai",
            r"mera aadhaar", r"enrolment no", r"\b\d{4}\s\d{4}\s\d{4}\b"
        ],
        DocumentType.PASSPORT: [
            r"republic of india", r"passport", r"passport no", r"type p"
        ],
        DocumentType.PAN: [
            r"income tax department", r"permanent account number", r"\b[a-z]{5}[0-9]{4}[a-z]{1}\b"
        ],
        DocumentType.VOTER_ID: [
            r"election commission", r"elector photo identity", r"voter id", r"epic"
        ],
        DocumentType.DRIVING_LICENCE: [
            r"driving licence", r"transport department", r"licence no", r"dl no"
        ],
        DocumentType.ADDRESS_PROOF: [
            r"electricity bill", r"bank statement", r"rent agreement", r"utility bill"
        ],
    }

    def classify(self, text: str) -> Tuple[DocumentType, float]:
        """
        Classifies document text and returns (DocumentType, confidence).
        """
        if not text or len(text.strip()) < 10:
            return DocumentType.UNKNOWN, 0.0

        text_lower = text.lower()
        type_scores: Dict[DocumentType, float] = {}

        for doc_type, patterns in self.KEYWORD_MAP.items():
            matches = sum(1 for p in patterns if re.search(p, text_lower))
            if matches > 0:
                score = min(1.0, max(0.4, matches / len(patterns)))
                type_scores[doc_type] = score

        if not type_scores:
            return DocumentType.UNKNOWN, 0.2

        best_type = max(type_scores, key=type_scores.get)
        confidence = type_scores[best_type]

        if confidence < 0.35:
            return DocumentType.UNKNOWN, round(confidence, 2)

        return best_type, round(confidence, 2)


class FieldExtractor:
    """
    Extracts structured key-value fields (name, dob, gender, address, document reference) from user documents.
    """

    def extract_fields(self, text: str, doc_type: DocumentType, page_number: int = 1) -> Dict[str, ExtractedField]:
        """
        Extracts document-specific fields with privacy sanitization.
        """
        fields: Dict[str, ExtractedField] = {}
        if not text:
            return fields

        # 1. Gender Extraction
        gender_match = re.search(r"\b(MALE|FEMALE|TRANSGENDER)\b", text, re.IGNORECASE)
        if gender_match:
            fields["gender"] = ExtractedField(
                field_name="gender",
                value=gender_match.group(1).upper(),
                confidence=0.95,
                page_number=page_number,
            )

        # 2. Date of Birth / Year of Birth
        dob_match = re.search(r"\b(DOB|Date of Birth|Birth Date)[:\s]+(\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})\b", text, re.IGNORECASE)
        if dob_match:
            fields["dob"] = ExtractedField(
                field_name="dob",
                value=dob_match.group(2),
                confidence=0.92,
                page_number=page_number,
            )
        else:
            yob_match = re.search(r"\b(Year of Birth|YOB)[:\s]+(\d{4})\b", text, re.IGNORECASE)
            if yob_match:
                fields["dob"] = ExtractedField(
                    field_name="dob",
                    value=yob_match.group(2),
                    confidence=0.85,
                    page_number=page_number,
                )

        # 3. Name Extraction
        name_match = re.search(r"\b(Name|To)[:\s]+([A-Za-z\s]{3,35})\b", text)
        if name_match:
            clean_name = name_match.group(2).strip()
            if len(clean_name) > 3 and not re.search(r"(government|authority|india)", clean_name, re.IGNORECASE):
                fields["name"] = ExtractedField(
                    field_name="name",
                    value=clean_name,
                    confidence=0.88,
                    page_number=page_number,
                )

        # 4. Document Reference Number (Masked for privacy)
        if doc_type == DocumentType.AADHAAR or re.search(r"\b\d{4}\s?\d{4}\s?\d{4}\b", text):
            aadhaar_match = re.search(r"\b(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})\b", text)
            if aadhaar_match:
                raw_num = f"{aadhaar_match.group(1)}{aadhaar_match.group(2)}{aadhaar_match.group(3)}"
                masked_num = f"XXXX-XXXX-{aadhaar_match.group(3)}"
                fields["masked_aadhaar"] = ExtractedField(
                    field_name="masked_aadhaar",
                    value=masked_num,
                    confidence=0.95,
                    page_number=page_number,
                )
                logger.info(f"Privacy Safe Log: Extracted masked Aadhaar reference: '{masked_num}'")

        elif doc_type == DocumentType.PAN:
            pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b", text)
            if pan_match:
                pan_val = pan_match.group(1)
                masked_pan = f"{pan_val[:2]}XXX{pan_val[5:]}"
                fields["pan_number"] = ExtractedField(
                    field_name="pan_number",
                    value=masked_pan,
                    confidence=0.95,
                    page_number=page_number,
                )

        # 5. Address Extraction
        addr_match = re.search(r"\b(Address|S/O|D/O|W/O)[:\s]+([\s\S]{10,120}?)(?=\d{6}|\b\d{4}\s\d{4}\b|\n\n|$)", text, re.IGNORECASE)
        if addr_match:
            fields["address"] = ExtractedField(
                field_name="address",
                value=addr_match.group(2).strip().replace("\n", " "),
                confidence=0.80,
                page_number=page_number,
            )

        return fields
