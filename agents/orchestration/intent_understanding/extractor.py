from __future__ import annotations

import re
from typing import Any

from agents.orchestration.intent_understanding.taxonomy import ENTITY_TYPES, UPDATE_TARGET_KEYWORDS


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().split()).lower()


def _strip_optional_suffix(value: str) -> str:
    return re.sub(r"[.;!?]+$", "", value or "").strip()


def _as_entity(entity_type: str, value: str, original_text: str | None = None) -> dict[str, Any]:
    cleaned = _strip_optional_suffix(value)
    return {
        "entity_type": entity_type,
        "value": cleaned,
        "normalized_value": normalize_text(cleaned),
        "confidence": 0.9,
        "source_text": original_text or cleaned,
    }


def _detect_mobile_number(value: str) -> str | None:
    match = re.search(
        r"(?:mobile(?:\s+number)?|phone(?:\s+number)?|(?:new\s+)?number)\s*(?:is|:|=)?\s*(\+?\d[\d\s().-]{7,}\d)",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        candidate = match.group(1).strip()
        if re.search(r"\d", candidate):
            return candidate
    return None


def _detect_email(value: str) -> str | None:
    match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", value)
    if match:
        return match.group(0)
    return None


def _detect_aadhaar_number(value: str) -> str | None:
    match = re.search(r"\b\d{12}\b", value)
    if match:
        return match.group(0)
    return None


def _detect_pincode(value: str) -> str | None:
    candidates = set(re.findall(r"\b[1-9][0-9]{5}\b", value))
    return next(iter(candidates)) if len(candidates) == 1 else None


def _detect_address_value(value: str) -> str | None:
    if not value or not value.strip():
        return None
    patterns = [
        # Explicit markers: new address: ..., address is ..., address to ...
        r"(?:address\s+(?:changed|updated|modified)\s+from\b.*?\bto\s*|new\s+address\s*(?:is|was|=|:)?|update\s+(?:my\s+)?(?:aadhaar\s+)?address\s+(?:to|is|with)\s*[:=-]?|change\s+(?:my\s+)?(?:aadhaar\s+)?address\s+(?:to|is|with)\s*[:=-]?|modify\s+(?:my\s+)?(?:aadhaar\s+)?address\s+(?:to|is|with)\s*[:=-]?|address\s*(?:is|was|=|:))\s*([A-Za-z0-9#][\s\S]+)",
        # Conversational markers: shifted to ..., moved to ..., living at ...
        r"(?:shifted\s+to|moved\s+to|living\s+at|residing\s+at)\s*([A-Za-z0-9#][\s\S]+)",
        # Sentence structures like "Aadhaar address update. 311 Bazaar Street..." or "Change Aadhaar address - 311 Bazaar Street..."
        r"(?:aadhaar\s+address\s+(?:update|change)|change\s+aadhaar\s+address)\s*[-–—.]\s*([A-Za-z0-9#][\s\S]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            # If candidate starts with phrasing like "changed from old one to...", extract part after "to"
            from_to_match = re.search(r"^(?:(?:changed|updated|modified)\s+)?\bfrom\b.*?\bto\s+(.+)", candidate, flags=re.IGNORECASE | re.DOTALL)
            if from_to_match:
                candidate = from_to_match.group(1).strip()
            # Clean trailing PIN prefix, PIN digits, and trailing text/punctuation
            candidate = re.sub(r"(?:,\s*)?(?:pin\s*(?:code)?)?\s*[-–—\s]*\b[1-9]\d{5}\b.*$", "", candidate, flags=re.IGNORECASE)
            # Cut off trailing sentence delimiters or action requests like "Please update..."
            candidate = re.split(r"(?:\.|\b)(?:please\s+)?(?:update|change|modify)\b", candidate, flags=re.IGNORECASE)[0].strip()
            candidate = candidate.strip(" .,-–—;:")
            norm_cand = candidate.lower()
            if (
                candidate
                and len(candidate) >= 3
                and not re.fullmatch(r"(?:address|new address|location|my aadhaar address|aadhaar address)", norm_cand)
                and not norm_cand.startswith("my aadhaar address")
                and not norm_cand.startswith("aadhaar address")
                and not norm_cand.startswith("wrong")
            ):
                return candidate

    # Multiline check: if message contains address update intent and has multiple lines, inspect remaining lines
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) > 1:
        first_line = lines[0].lower()
        if any(w in first_line for w in ("update", "change", "address", "shifted", "moved")):
            candidate_lines = lines[1:]
            candidate = "\n".join(candidate_lines)
            candidate = re.sub(r"(?:,\s*)?(?:pin\s*(?:code)?)?\s*[-–—\s]*\b[1-9]\d{5}\b.*$", "", candidate, flags=re.IGNORECASE)
            candidate = re.split(r"(?:\.|\b)(?:please\s+)?(?:update|change|modify)\b", candidate, flags=re.IGNORECASE)[0].strip()
            candidate = candidate.strip(" .,-–—;:")
            if candidate and len(candidate) >= 3:
                return candidate

    return None


def _detect_name(value: str) -> str | None:
    match = re.search(r"(?:my\s+)?name\s+(?:is|=|:)?\s*([A-Za-z][A-Za-z'\-\. ]{1,60})", value, flags=re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        if candidate and not candidate.lower().startswith("name"):
            return candidate
    return None


def _detect_date_of_birth(value: str) -> str | None:
    patterns = [
        r"(?:date\s+of\s+birth|dob|birth\s+date)\s*(?:is|=|:)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:date\s+of\s+birth|dob|birth\s+date)\s*(?:is|=|:)?\s*(\d{4}-\d{2}-\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _detect_gender(value: str) -> str | None:
    match = re.search(r"\bgender\s*(?:is|=|:)?\s*(male|female|other)\b", value, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extract_entities(value: str, previous_target: str | None = None, session_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    text = value or ""
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()

    explicit_target = previous_target
    if not explicit_target and session_state:
        explicit_target = session_state.get("update_type") or session_state.get("target")

    def add(entity_type: str, raw_value: str | None, source_text: str | None = None) -> None:
        if not raw_value:
            return
        key = (entity_type, normalize_text(raw_value))
        if key in seen:
            return
        seen.add(key)
        entities.append(_as_entity(entity_type, raw_value, source_text or raw_value))

    add("aadhaar_number", _detect_aadhaar_number(text), text)
    detected_addr = _detect_address_value(text)
    add("address", detected_addr, text)
    add("pincode", _detect_pincode(text), text)
    add("mobile_number", _detect_mobile_number(text), text)
    add("email", _detect_email(text), text)
    add("name", _detect_name(text), text)
    add("date_of_birth", _detect_date_of_birth(text), text)
    add("gender", _detect_gender(text), text)

    if explicit_target and explicit_target != "unknown" and not any(entity["entity_type"] == explicit_target for entity in entities):
        if explicit_target == "address":
            address_value = _detect_address_value(text)
            if address_value:
                add("address", address_value, text)
        elif explicit_target == "mobile_number":
            mobile_value = _detect_mobile_number(text)
            if mobile_value:
                add("mobile_number", mobile_value, text)
        elif explicit_target == "email":
            email_value = _detect_email(text)
            if email_value:
                add("email", email_value, text)
        elif explicit_target == "name":
            name_value = _detect_name(text)
            if name_value:
                add("name", name_value, text)
        elif explicit_target == "date_of_birth":
            dob_value = _detect_date_of_birth(text)
            if dob_value:
                add("date_of_birth", dob_value, text)
        elif explicit_target == "gender":
            gender_value = _detect_gender(text)
            if gender_value:
                add("gender", gender_value, text)

    return entities


def extract_signals(value: str) -> tuple[list[str], list[str], list[dict[str, Any]], str]:
    text = value or ""
    intent_signals: list[str] = []
    update_signals: list[str] = []
    for intent_name, keywords in {
        "status_inquiry": ("status", "check status", "track status", "what is the status"),
        "update_request": ("update", "change", "modify"),
        "correction_request": ("correct", "correction", "fix"),
        "document_request": ("document", "certificate", "form"),
        "complaint": ("problem", "issue", "complaint"),
        "enrollment": ("enroll", "registration"),
        "general_assistance": ("help", "support", "assistance"),
    }.items():
        if any(keyword in normalize_text(text) for keyword in keywords):
            intent_signals.append(intent_name)

    for target_name, keywords in UPDATE_TARGET_KEYWORDS.items():
        if any(keyword in normalize_text(text) for keyword in keywords):
            update_signals.append(target_name)

    entities = extract_entities(text)
    urgency = "normal"
    if any(keyword in normalize_text(text) for keyword in ("urgent", "immediate", "problem", "issue")):
        urgency = "high"
    return intent_signals, update_signals, entities, urgency
