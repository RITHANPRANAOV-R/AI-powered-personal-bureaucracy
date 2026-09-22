from __future__ import annotations

from typing import List, Tuple

from .schemas import ExtractedEntity
from .taxonomy import ENTITY_KEYWORDS, INTENT_KEYWORDS, URGENCY_KEYWORDS, UpdateType


def normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _extract_keyword_entity(entity_type: str, text: str) -> ExtractedEntity | None:
    normalized = normalize_text(text)
    keywords = ENTITY_KEYWORDS.get(entity_type, [])
    if not keywords:
        return None
    if any(keyword in normalized for keyword in keywords):
        value = next(keyword for keyword in keywords if keyword in normalized)
        return ExtractedEntity(
            entity_type=entity_type,
            value=value,
            normalized_value=value,
            confidence=0.8,
            source_text=value,
        )
    return None


def extract_signals(message: str) -> tuple[list[str], list[str], list[ExtractedEntity], str]:
    normalized = normalize_text(message)
    intent_signals: list[str] = []
    update_signals: list[str] = []
    entities: list[ExtractedEntity] = []

    for intent_name, keywords in INTENT_KEYWORDS.items():
        if _contains_any(normalized, keywords):
            intent_signals.append(intent_name.value)

    for update_name, keywords in {
        "address": ["address", "residence"],
        "mobile_number": ["mobile", "phone number", "mobile number"],
        "email": ["email", "e-mail"],
        "name": ["name"],
        "date_of_birth": ["date of birth", "dob", "birth date"],
        "gender": ["gender"],
        "biometric": ["biometric", "fingerprint", "iris"],
    }.items():
        if _contains_any(normalized, keywords):
            update_signals.append(update_name)

    for entity_name in [
        "aadhaar_number",
        "address",
        "mobile_number",
        "email",
        "name",
        "date_of_birth",
        "gender",
        "document",
        "location",
        "reference_date",
        "issue_category",
    ]:
        item = _extract_keyword_entity(entity_name, normalized)
        if item is not None and not any(existing.entity_type == item.entity_type for existing in entities):
            entities.append(item)

    if _contains_any(normalized, URGENCY_KEYWORDS):
        urgency = "high"
    else:
        urgency = "normal"

    return intent_signals, update_signals, entities, urgency


def extract_entities(message: str) -> list[ExtractedEntity]:
    _, _, entities, _ = extract_signals(message)
    return entities
