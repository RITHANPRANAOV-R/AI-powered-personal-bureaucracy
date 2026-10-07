"""
Document Classifier and Field Extractor for User Document Understanding.
Extracted field values are preserved with confidence scores, page provenance, and privacy-safe logging.
"""
import re
import logging
from typing import Tuple, Dict, Any, Optional, List
from agents.knowledge_based.information_retrieval.schemas.user_document import (
    DocumentType,
    ExtractedField,
)
from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import OCRLine

logger = logging.getLogger(__name__)


class DocumentClassifier:
    """
    Classifies raw extracted text into standard document categories.
    """

    KEYWORD_MAP = {
        DocumentType.AADHAAR: [
            r"unique identification", r"authority of india", r"aadhaar", r"aadhar", r"adhar",
            r"uidai", r"mera aadhaar", r"my aadhaar", r"enrolment", r"enrollment",
            r"government of india", r"bharat sarkar", r"\b\d{4}\s?\d{4}\s?\d{4}\b",
            r"\b[xX]{4}[\s-]?[xX]{4}[\s-]?\d{4}\b", r"\bvid\b", r"virtual id"
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


DISALLOWED_NAME_WORDS = {
    # Labels & Field Names
    "name", "nam", "naam", "mobile", "phone", "email", "mail", "contact", "tel", "telephone",
    "pin", "pincode", "vid", "uid", "uidai", "no", "number", "num",
    "dob", "date", "birth", "year", "yob", "age",
    "gender", "sex", "male", "female", "transgender", "purush", "mahila", "tritiyapanthi",
    "address", "pata", "to", "from", "signature", "signed", "digitally",
    "valid", "invalid", "help", "helpline", "toll", "free", "www", "http", "https",
    "com", "gov", "in", "org", "net",
    # Government & Entity names
    "aadhaar", "aadhar", "adhar", "mera", "meri", "pehchan", "pehechan",
    "bharat", "india", "sarkar", "government", "govt", "authority",
    "unique", "identification", "enrolment", "enrollment", "update", "updated",
    "years", "year", "after", "every", "electronically", "generated", "information",
    "details", "card", "cardholder", "republic", "income", "tax", "permanent",
    "account", "elector", "photo", "identity", "driving", "licence", "license",
    "transport", "commission", "election", "state", "union", "national", "portal",
    "download", "resident", "citizen", "instruction", "instructions", "note",
    "important", "qr", "code", "secure", "offline", "verification", "xml", "masked",
    "father", "mother", "husband", "wife", "son", "daughter", "guardian", "care",
    "house", "flat", "street", "road", "nagar", "sector", "city", "district",
    "bureaucracy", "document", "copy", "original", "proof", "citizenship",
    "pradhikaran", "vishisht", "aam", "aadmi", "adhikar", "dept", "department",
    "helpdesk", "online", "services", "service", "portal", "issued", "issue",
    "should", "been", "with", "have", "your", "this", "that", "these", "those",
    "about", "above", "below", "other", "such", "there", "their", "which", "where",
}

ADDRESS_BOILERPLATE_PATTERNS = [
    r"should\s+be\s+updated",
    r"after\s+every\s+\d+\s+years",
    r"date\s+of\s+enrolment",
    r"date\s+of\s+enrollment",
    r"enrolment\s+no",
    r"enrollment\s+no",
    r"aadhaar\s+helps\s+you",
    r"government\s+benefits",
    r"government\s+services",
    r"keep\s+your\s+mobile",
    r"updated\s+in\s+aadhaar",
    r"proof\s+of\s+identity",
    r"not\s+of\s+citizenship",
    r"not\s+a\s+proof\s+of\s+citizenship",
    r"aadhaarisproofofidentity",
    r"aadhaar\s*is\s*proof",
    r"identity\.notofcitizenship",
    r"citizenshipordateofbirth",
    r"dob\.dob",
    r"help@uidai",
    r"www\.uidai",
    r"toll\s+free",
    r"1947",
    r"unique\s+identification\s+authority",
    r"bharat\s+sarkar",
    r"government\s+of\s+india",
    r"mera\s+aadhaar",
    r"meri\s+pehchan",
    r"download\s+date",
    r"generation\s+date",
    r"digitally\s+signed",
    r"electronic\s+signature",
    r"validity\s+unknown",
    r"signature\s+valid",
    r"valid\s+only\s+with",
    r"information\s+on\s+this\s+card",
]


class FieldExtractor:
    """
    Extracts structured key-value fields (name, dob, gender, address, document reference) from user documents.
    """

    def extract_fields(
        self, text: str, doc_type: DocumentType, page_number: int = 1, ocr_lines: Optional[List[OCRLine]] = None
    ) -> Dict[str, ExtractedField]:
        """
        Extracts document-specific fields with privacy sanitization.
        """
        fields: Dict[str, ExtractedField] = {}
        if not text:
            return fields

        # 1. Gender Extraction
        gender_field = self._extract_gender(text, page_number)
        if gender_field:
            fields["gender"] = gender_field

        # 2. Date of Birth / Year of Birth
        dob_field = self._extract_dob(text, page_number)
        if dob_field:
            fields["dob"] = dob_field

        # 3. Document Reference Number (Masked, full 12-digit, and VID)
        if doc_type == DocumentType.AADHAAR or re.search(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", text) or re.search(r"[xX]{4}[\s-]?[xX]{4}[\s-]?\d{4}", text) or re.search(r"\bVID\b", text, re.I):
            vid_field = self._extract_vid(text, page_number)
            if vid_field:
                fields["vid"] = vid_field

            masked_aadhaar_field = self._extract_masked_aadhaar(text, page_number)
            if masked_aadhaar_field:
                fields["masked_aadhaar"] = masked_aadhaar_field

            full_aadhaar_field = self._extract_aadhaar_number(text, page_number)
            if full_aadhaar_field:
                fields["aadhaar_number"] = full_aadhaar_field

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

        # 4. Name Extraction
        name_field = self._extract_name(text, page_number)
        if name_field:
            fields["name"] = name_field

        # 5. Address Extraction
        address_field = self._extract_address(text, page_number, ocr_lines=ocr_lines)
        if address_field:
            fields["address"] = address_field

        return fields

    def _extract_gender(self, text: str, page_number: int) -> Optional[ExtractedField]:
        explicit = re.search(r"(?:Gender|लिंग|Sex)[:\s/]+(MALE|FEMALE|TRANSGENDER|पुरुष|महिला|तृतीयपंथी)", text, re.IGNORECASE)
        if explicit:
            raw_val = explicit.group(1).strip().upper()
            norm_val = "MALE" if raw_val in {"MALE", "पुरुष"} else "FEMALE" if raw_val in {"FEMALE", "महिला"} else "TRANSGENDER" if raw_val in {"TRANSGENDER", "तृतीयपंथी"} else raw_val
            return ExtractedField(field_name="gender", value=norm_val, confidence=0.98, page_number=page_number)

        standalone = re.search(r"\b(MALE|FEMALE|TRANSGENDER|पुरुष|महिला)\b", text, re.IGNORECASE)
        if standalone:
            raw_val = standalone.group(1).strip().upper()
            norm_val = "MALE" if raw_val in {"MALE", "पुरुष"} else "FEMALE" if raw_val in {"FEMALE", "महिला"} else "TRANSGENDER"
            return ExtractedField(field_name="gender", value=norm_val, confidence=0.95, page_number=page_number)
        return None

    def _parse_and_validate_date(self, raw_date_str: str) -> Optional[str]:
        cleaned = re.sub(r"\s+", "", raw_date_str).replace("-", "/").replace(".", "/")
        parts = cleaned.split("/")
        if len(parts) == 3:
            try:
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                if 1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2025:
                    return f"{d:02d}/{m:02d}/{y:04d}"
            except ValueError:
                pass
        return None

    def _extract_dob(self, text: str, page_number: int) -> Optional[ExtractedField]:
        # 1. Regex search across normalized text for labeled DOB
        dob_labeled = re.search(
            r"(?:DOB|Date\s+of\s+Birth|Birth\s+Date|D\.?\s*O\.?\s*B\.?|जन्म\s*तिथि|जन्म\s*तारीख|जन्म\s*दिनांक)[\s/:\-–—\n]+(\d{1,2}\s*[/.\-\s]\s*\d{1,2}\s*[/.\-\s]\s*\d{4})",
            text,
            re.IGNORECASE,
        )
        if dob_labeled:
            parsed = self._parse_and_validate_date(dob_labeled.group(1))
            if parsed:
                return ExtractedField(field_name="dob", value=parsed, confidence=0.95, page_number=page_number)

        # 2. Line-by-line lookahead if label and date are split across lines
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for idx, line in enumerate(lines):
            if re.search(r"\b(?:DOB|Date\s+of\s+Birth|Birth\s+Date|D\.?\s*O\.?\s*B\.?|जन्म\s*तिथि|जन्म\s*तारीख|जन्म\s*दिनांक)\b", line, re.IGNORECASE):
                date_match = re.search(r"(\d{1,2}\s*[/.\-\s]\s*\d{1,2}\s*[/.\-\s]\s*\d{4})", line)
                if date_match:
                    parsed = self._parse_and_validate_date(date_match.group(1))
                    if parsed:
                        return ExtractedField(field_name="dob", value=parsed, confidence=0.95, page_number=page_number)
                for next_idx in range(idx + 1, min(len(lines), idx + 3)):
                    next_line = lines[next_idx]
                    date_match = re.search(r"(\d{1,2}\s*[/.\-\s]\s*\d{1,2}\s*[/.\-\s]\s*\d{4})", next_line)
                    if date_match:
                        parsed = self._parse_and_validate_date(date_match.group(1))
                        if parsed:
                            return ExtractedField(field_name="dob", value=parsed, confidence=0.92, page_number=page_number)

        # 3. Year of birth patterns
        yob_labeled = re.search(
            r"(?:Year\s+of\s+Birth|YOB|जन्म\s*का\s*वर्ष|जन्म\s*वर्ष)[\s/:\-–—\n]+(\d{4})",
            text,
            re.IGNORECASE,
        )
        if yob_labeled:
            year = yob_labeled.group(1).strip()
            if 1900 <= int(year) <= 2025:
                return ExtractedField(field_name="dob", value=year, confidence=0.90, page_number=page_number)

        # 4. Fallback search for standalone date in document
        for match in re.finditer(r"\b(0?[1-9]|[12]\d|3[01])\s*[/.-]\s*(0?[1-9]|1[0-2])\s*[/.-]\s*(19\d{2}|20[0-2]\d)\b", text):
            start_ctx = max(0, match.start() - 30)
            context = text[start_ctx:match.start()].lower()
            if any(k in context for k in ["download", "generation", "issued", "valid", "update"]):
                continue
            parsed = self._parse_and_validate_date(match.group(0))
            if parsed:
                return ExtractedField(field_name="dob", value=parsed, confidence=0.85, page_number=page_number)

        return None

    def _extract_vid(self, text: str, page_number: int) -> Optional[ExtractedField]:
        # 1. Explicit VID context / label
        vid_match = re.search(
            r"(?:VID|Virtual\s+ID|Virtual\s+ID\s*\(VID\)|वीआईडी|विर्चुअल\s+आईडी)\s*[:\s-]*\s*(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b",
            text,
            re.IGNORECASE,
        )
        if vid_match:
            raw = re.sub(r"[\s-]", "", vid_match.group(1))
            if len(raw) == 16:
                formatted = f"{raw[:4]} {raw[4:8]} {raw[8:12]} {raw[12:]}"
                return ExtractedField(field_name="vid", value=formatted, confidence=0.95, page_number=page_number)

        # 2. Fallback: 16-digit sequence preceded within 50 chars by VID / Virtual ID keyword
        for match in re.finditer(r"\b(\d{4})[\s-]+(\d{4})[\s-]+(\d{4})[\s-]+(\d{4})\b", text):
            start_ctx = max(0, match.start() - 50)
            context = text[start_ctx:match.start()].lower()
            if any(k in context for k in ["vid", "virtual", "वीआईडी", "विर्चुअल"]):
                val = f"{match.group(1)} {match.group(2)} {match.group(3)} {match.group(4)}"
                return ExtractedField(field_name="vid", value=val, confidence=0.92, page_number=page_number)

        return None

    def _extract_masked_aadhaar(self, text: str, page_number: int) -> Optional[ExtractedField]:
        # Only match actual masked Aadhaar patterns (e.g. XXXX XXXX 7418 or XXXX-XXXX-7418)
        # NEVER convert full Aadhaar numbers into masked Aadhaar.
        masked_match = re.search(r"\b(?:[xX]{4}|[•*]{4})[\s-]*(?:[xX]{4}|[•*]{4})[\s-]*(\d{4})\b", text)
        if masked_match:
            last4 = masked_match.group(1)
            return ExtractedField(
                field_name="masked_aadhaar",
                value=f"XXXX XXXX {last4}",
                confidence=0.95,
                page_number=page_number,
            )
        return None

    def _extract_aadhaar_number(self, text: str, page_number: int) -> Optional[ExtractedField]:
        # RULE 1: A 16-digit VID must NEVER populate aadhaar_number.
        # RULE 2: A masked Aadhaar must NEVER be converted or inferred into a full Aadhaar number.
        # RULE 3: If document contains only masked Aadhaar and no genuine unmasked 12-digit Aadhaar number, aadhaar_number = None.
        lines = text.split("\n")
        for line in lines:
            line_str = line.strip()
            # Ignore lines that are explicitly labeled as VID
            if re.search(r"\b(?:VID|Virtual\s+ID|वीआईडी|विर्चुअल\s+आईडी)\b", line_str, re.IGNORECASE):
                continue

            # Look for 3 blocks of 4 digits
            for m in re.finditer(r"\b(\d{4})[\s-]+(\d{4})[\s-]+(\d{4})\b", line_str):
                # Check if followed by a 4th block of 4 digits (which would make it a 16-digit VID)
                after_text = line_str[m.end():]
                if re.match(r"^[\s-]*\d{4}\b", after_text):
                    continue  # It's part of a 16-digit VID! Ignore.

                # Check if preceded by VID / Virtual ID / Enrolment context
                before_text = line_str[:m.start()].lower()
                if any(kw in before_text for kw in ["vid", "virtual", "enrolment", "enrollment"]):
                    continue

                val = f"{m.group(1)} {m.group(2)} {m.group(3)}"
                return ExtractedField(
                    field_name="aadhaar_number",
                    value=val,
                    confidence=0.95,
                    page_number=page_number,
                )

            # Look for 12 continuous digits
            for m in re.finditer(r"(?<!\d)(\d{12})(?!\d)", line_str):
                before_text = line_str[:m.start()].lower()
                after_text = line_str[m.end():].lower()
                if any(kw in before_text for kw in ["vid", "virtual", "enrolment", "enrollment"]):
                    continue
                if re.match(r"^\d{4}\b", after_text):  # 16 digits
                    continue
                raw_num = m.group(1)
                val = f"{raw_num[:4]} {raw_num[4:8]} {raw_num[8:]}"
                return ExtractedField(
                    field_name="aadhaar_number",
                    value=val,
                    confidence=0.92,
                    page_number=page_number,
                )

        return None

    def _is_valid_name(self, candidate: str) -> bool:
        if not candidate:
            return False
        cand = candidate.strip()
        
        # Reject candidates containing metadata delimiters or symbols
        if re.search(r"[:;@=<>_{}[\]~*^%$#+\\/0-9]", cand):
            return False
        if re.search(r"\b(?:http|https|www|\.com|\.in|\.gov|\.org)\b", cand, re.IGNORECASE):
            return False

        # Extract alphabetic words
        words = re.findall(r"[A-Za-z]+", cand)
        if not words or len(words) > 5:
            return False

        full_str = " ".join(words)
        if len(full_str) < 3 or len(full_str) > 40:
            return False

        # Check disallowed words
        lower_words = [w.lower() for w in words]
        for w in lower_words:
            if w in DISALLOWED_NAME_WORDS:
                return False

        # Check whole phrase blacklist
        lower_full = full_str.lower()
        for phrase in [
            "government of india", "unique identification", "authority of india",
            "bharat sarkar", "mera aadhaar", "meri pehchan", "date of birth",
            "proof of identity", "keep your mobile", "helpdesk",
        ]:
            if phrase in lower_full:
                return False

        # If 1-word candidate:
        if len(words) == 1:
            w = words[0]
            if len(w) < 3:
                return False
            if not (w.isupper() or (w[0].isupper() and w[1:].islower())):
                return False

        return True

    def _clean_name(self, candidate: str) -> str:
        cand = candidate.strip()
        cand = re.sub(r"^[^A-Za-z]+", "", cand)
        cand = re.sub(r"[^A-Za-z\s.'-]", "", cand)
        return " ".join(cand.split())

    def _extract_name(self, text: str, page_number: int) -> Optional[ExtractedField]:
        # Strategy 1: Explicit Label "Name: John Doe" or "नाम: John Doe"
        explicit = re.search(r"(?:Name|नाम)\s*[:\s-]+\s*([A-Za-z\s.'-]{3,40})(?=\n|$)", text, re.IGNORECASE)
        if explicit and self._is_valid_name(explicit.group(1)):
            return ExtractedField(
                field_name="name",
                value=self._clean_name(explicit.group(1)),
                confidence=0.95,
                page_number=page_number,
            )

        # Strategy 2: e-Aadhaar "To," block
        to_match = re.search(r"\bTo[\s,]*\n+([A-Za-z\s.'-]{3,40})(?=\n|$)", text, re.IGNORECASE)
        if to_match and self._is_valid_name(to_match.group(1)):
            return ExtractedField(
                field_name="name",
                value=self._clean_name(to_match.group(1)),
                confidence=0.92,
                page_number=page_number,
            )

        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Strategy 3: Line preceding DOB / Gender / Relation
        for idx, line in enumerate(lines):
            if re.search(r"(DOB|Date\s+of\s+Birth|Birth\s+Date|जन्म\s*तिथि|जन्म\s*तारीख|\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|लिंग|Gender|\b(?:MALE|FEMALE|TRANSGENDER)\b)", line, re.IGNORECASE):
                for back_idx in range(idx - 1, max(-1, idx - 4), -1):
                    cand = lines[back_idx]
                    if self._is_valid_name(cand):
                        return ExtractedField(
                            field_name="name",
                            value=self._clean_name(cand),
                            confidence=0.88,
                            page_number=page_number,
                        )

        # Strategy 4: Line following Government of India / Bharat Sarkar header
        for idx, line in enumerate(lines):
            if re.search(r"(Government\s+of\s+India|भारत\s+सरकार|Unique\s+Identification\s+Authority)", line, re.IGNORECASE):
                for fwd_idx in range(idx + 1, min(len(lines), idx + 4)):
                    cand = lines[fwd_idx]
                    if self._is_valid_name(cand):
                        return ExtractedField(
                            field_name="name",
                            value=self._clean_name(cand),
                            confidence=0.85,
                            page_number=page_number,
                        )

        # Strategy 5: Line preceding relation marker S/O, D/O, W/O, C/O
        for idx, line in enumerate(lines):
            if re.search(r"\b(?:S/O|D/O|W/O|C/O|Care\s+of)[:\s]", line, re.IGNORECASE) and idx > 0:
                cand = lines[idx - 1]
                if self._is_valid_name(cand):
                    return ExtractedField(
                        field_name="name",
                        value=self._clean_name(cand),
                        confidence=0.85,
                        page_number=page_number,
                    )

        return None

    def _is_address_boilerplate(self, line_or_text: str) -> bool:
        lower = line_or_text.lower()
        return any(re.search(pat, lower) for pat in ADDRESS_BOILERPLATE_PATTERNS)

    def _validate_address(self, addr_str: str) -> bool:
        if not addr_str or len(addr_str) < 12:
            return False
        if self._is_address_boilerplate(addr_str):
            return False

        has_pin = bool(re.search(r"\b[1-9]\d{5}\b", addr_str))
        has_address_keywords = bool(re.search(
            r"\b(street|road|nagar|colony|sector|house|flat|building|floor|layout|cross|lane|"
            r"apartment|near|opp|opposite|behind|district|city|state|village|taluk|tehsil|"
            r"post|po|ps|dist|s/o|w/o|c/o|d/o|bhavan|marg|gali|ward|bengaluru|bangalore|"
            r"chennai|mumbai|delhi|kolkata|hyderabad|karnataka|tamil\s+nadu|maharashtra|"
            r"kerala|telangana|andhra\s+pradesh|uttar\s+pradesh|west\s+bengal|rajasthan|"
            r"gujarat|punjab|haryana|bihar|odisha|assam|jharkhand|uttarakhand|goa)\b",
            addr_str,
            re.IGNORECASE,
        ))

        if has_pin and (has_address_keywords or len(addr_str) >= 20):
            return True
        if has_address_keywords and len(addr_str) >= 25:
            return True

        return False

    def _clean_address_lines(self, lines: list[str]) -> list[str]:
        cleaned = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if self._is_address_boilerplate(line_str):
                break
            if re.search(r"\b(\d{4}\s\d{4}\s\d{4}|[xX]{4}[\s-][xX]{4}[\s-]\d{4}|\d{4}\s\d{4}\s\d{4}\s\d{4})\b", line_str):
                break
            line_str = re.sub(r"^(?:Address|पता|Address\s*[:\s-]*|पता\s*[:\s-]*)", "", line_str, flags=re.IGNORECASE).strip()
            # Strip inline boilerplate suffix if appended to address line
            for pat in ADDRESS_BOILERPLATE_PATTERNS:
                match = re.search(pat, line_str, flags=re.IGNORECASE)
                if match:
                    line_str = line_str[:match.start()].strip()
                    break
            clean_l = line_str.rstrip(",; ")
            if clean_l and not self._is_address_boilerplate(clean_l):
                cleaned.append(clean_l)
            if re.search(r"\b[1-9]\d{5}\b", line_str):
                break
        return cleaned

    def _extract_address(
        self, text: str, page_number: int, ocr_lines: Optional[List[OCRLine]] = None
    ) -> Optional[ExtractedField]:
        # Convert text to OCRLines if not provided
        lines: List[OCRLine] = []
        if ocr_lines:
            lines = ocr_lines
        else:
            for l in text.split("\n"):
                l_str = l.strip()
                if l_str:
                    lines.append(OCRLine(text=l_str, confidence=0.9, bbox=[], page_number=page_number))

        if not lines:
            return None

        anchor_regex = re.compile(
            r"^(?:Address|Address\s*[:\s-]|पता|पता\s*[:\s-]|S/O|D/O|W/O|C/O|R/O|Care\s+of)[:\s-]",
            re.IGNORECASE,
        )

        address_blocks: list[list[OCRLine]] = []

        for idx, line_obj in enumerate(lines):
            line_txt = line_obj.text.strip()
            if anchor_regex.search(line_txt) or re.search(r"\b(?:S/O|D/O|W/O|C/O|Care\s+of)[:\s]", line_txt, re.IGNORECASE):
                if self._is_address_boilerplate(line_txt):
                    continue

                current_block: list[OCRLine] = [line_obj]

                # Bounding box of anchor for horizontal column filtering
                anchor_x_range = None
                if line_obj.bbox and len(line_obj.bbox) >= 4:
                    xs = [pt[0] for pt in line_obj.bbox]
                    anchor_x_range = (min(xs) - 150.0, max(xs) + 350.0)

                # PIN STOP RULE: Check if anchor line already contains PIN code
                if re.search(r"\b[1-9]\d{5}\b", line_txt):
                    address_blocks.append(current_block)
                    continue

                for fwd_idx in range(idx + 1, len(lines)):
                    fwd_line = lines[fwd_idx]
                    fwd_txt = fwd_line.text.strip()
                    if not fwd_txt:
                        continue

                    # Column / spatial filtering using bounding box overlap
                    if anchor_x_range and fwd_line.bbox and len(fwd_line.bbox) >= 4:
                        fwd_xs = [pt[0] for pt in fwd_line.bbox]
                        fwd_min_x = min(fwd_xs)
                        if fwd_min_x < anchor_x_range[0] or fwd_min_x > anchor_x_range[1]:
                            # Unrelated column text! Ignore.
                            continue

                    # Stop conditions: next anchor, boilerplate, VID, Aadhaar number, UIDAI footer
                    if (anchor_regex.search(fwd_txt) or re.search(r"^(?:Address|पता)\b", fwd_txt, re.I)) and len(current_block) > 1:
                        break
                    if self._is_address_boilerplate(fwd_txt):
                        break
                    if re.search(r"\b(\d{4}\s\d{4}\s\d{4}|[xX]{4}[\s-][xX]{4}[\s-]\d{4}|\d{4}\s\d{4}\s\d{4}\s\d{4})\b", fwd_txt):
                        break
                    if re.search(r"\b(?:VID|Virtual\s+ID|Help|Helpline|Toll\s+Free|www\.uidai|help@uidai)\b", fwd_txt, re.IGNORECASE):
                        break

                    current_block.append(fwd_line)

                    # PIN STOP RULE: include the line containing the PIN code and STOP immediately
                    if re.search(r"\b[1-9]\d{5}\b", fwd_txt):
                        break

                if current_block:
                    address_blocks.append(current_block)

        # Select best validated address candidate block
        best_cleaned: list[str] = []
        for block in address_blocks:
            cleaned = self._clean_address_lines([l.text for l in block])
            if cleaned and len(", ".join(cleaned)) > len(", ".join(best_cleaned)):
                candidate_str = ", ".join(cleaned)
                if self._validate_address(candidate_str):
                    best_cleaned = cleaned

        if best_cleaned:
            addr_str = ", ".join(best_cleaned)
            addr_str = re.sub(r"\s*,\s*", ", ", addr_str)
            addr_str = re.sub(r"\s+", " ", addr_str).strip()
            return ExtractedField(field_name="address", value=addr_str, confidence=0.88, page_number=page_number)

        # General fallback if no anchor blocks were found
        return self._fallback_extract_address(text, page_number)

    def _fallback_extract_address(self, text: str, page_number: int) -> Optional[ExtractedField]:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        address_lines = []
        in_address = False

        for idx, line in enumerate(lines):
            if not in_address:
                if re.search(r"^(?:Address|पता|Address\s*[:\s-]|पता\s*[:\s-])", line, re.IGNORECASE):
                    if self._is_address_boilerplate(line):
                        continue
                    in_address = True
                    address_lines.append(line)
                    if re.search(r"\b[1-9]\d{5}\b", line):
                        break
            else:
                if self._is_address_boilerplate(line):
                    break
                if re.search(r"\b(\d{4}\s\d{4}\s\d{4}|[xX]{4}[\s-][xX]{4}[\s-]\d{4})\b", line):
                    break
                address_lines.append(line)
                if re.search(r"\b[1-9]\d{5}\b", line):
                    break

        if address_lines:
            cleaned = self._clean_address_lines(address_lines)
            if cleaned:
                addr_str = ", ".join(cleaned)
                addr_str = re.sub(r"\s*,\s*", ", ", addr_str)
                addr_str = re.sub(r"\s+", " ", addr_str).strip()
                if self._validate_address(addr_str):
                    return ExtractedField(field_name="address", value=addr_str, confidence=0.82, page_number=page_number)

        return None
