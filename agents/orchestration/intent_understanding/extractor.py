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


def _detect_address_value(value: str) -> str | None:
    patterns = [
        r"(?:new\s+)?address\s+(?:is|was|=|:)?\s*([A-Za-z0-9][A-Za-z0-9,\s.-]{1,120})",
        r"(?:my\s+)?address\s+(?:is|was|=|:)?\s*([A-Za-z0-9][A-Za-z0-9,\s.-]{1,120})",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate and not re.fullmatch(r"(?:address|new address)", candidate, flags=re.IGNORECASE):
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
    add("address", _detect_address_value(text), text)
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
