from __future__ import annotations

import re
from typing import Any

from agents.orchestration.intent_understanding.extractor import extract_entities, normalize_text
from agents.orchestration.intent_understanding.schemas import (
    ExtractedEntity,
    IntentClassificationResult,
    MissingInformation,
    UserRequestInput,
)
from agents.orchestration.intent_understanding.taxonomy import (
    INTENT_KEYWORDS,
    INTENT_TYPES,
    MISSING_FIELD_MAP,
    UPDATE_TARGET_KEYWORDS,
    UPDATE_TARGETS,
)


class IntentUnderstandingService:
    def process(self, request: UserRequestInput) -> IntentClassificationResult:
        raw_message = request.user_message or ""
        message = raw_message.strip()
        normalized = normalize_text(message)
        session_state = request.current_session_state or {}
        history_context = " ".join(request.conversation_history or []) if request.conversation_history else ""

        context_target = self._get_contextual_target(session_state, request.conversation_history)
        intent_type = self._classify_intent(message, context_target, session_state, request.conversation_history)
        update_type = self._classify_update_target(message, context_target, intent_type, request.conversation_history)
        entities = self._extract_entities(message, update_type, context_target, session_state)
        missing_information = self._identify_missing_information(intent_type, update_type, entities, message)
        urgency = self._resolve_urgency(intent_type, update_type, normalized)
        confidence = self._calculate_confidence(intent_type, update_type, entities, message, context_target)
        summary = self._build_summary(intent_type, update_type)

        return IntentClassificationResult(
            session_id=request.session_id,
            intent_type=intent_type,
            update_type=update_type,
            summary=summary,
            entities=entities,
            urgency=urgency,
            missing_information=missing_information,
            confidence=confidence,
        )

    def _get_contextual_target(self, session_state: dict[str, Any] | None, conversation_history: list[str] | None = None) -> str | None:
        if session_state:
            for key in ("update_type", "target", "active_target"):
                value = session_state.get(key)
                if isinstance(value, str) and value in UPDATE_TARGETS:
                    return value

        history_text = " ".join(conversation_history or [])
        if not history_text:
            return None
        normalized = normalize_text(history_text)
        for target_name, keywords in UPDATE_TARGET_KEYWORDS.items():
            if any(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized) for keyword in keywords):
                return target_name
        return None

    def _classify_intent(self, message: str, context_target: str | None, session_state: dict[str, Any] | None, conversation_history: list[str] | None = None) -> str:
        normalized = normalize_text(message)
        if not normalized:
            return "general_assistance"

        history_text = " ".join(conversation_history or [])
        history_normalized = normalize_text(history_text)
        history_intent = self._infer_intent_from_history(history_normalized)
        if history_intent and not any(word in normalized for word in ("status", "problem", "complaint", "correct", "document", "update", "change", "help", "enroll", "support", "assistance")):
            return history_intent

        if session_state and session_state.get("intent_type") in {"update_request", "correction_request", "status_inquiry", "document_request", "complaint", "enrollment"} and not any(word in normalized for word in ("status", "problem", "complaint", "correct", "document", "update", "change", "help")):
            prior_intent = session_state.get("intent_type")
            if prior_intent in {"update_request", "correction_request"}:
                return prior_intent

        for intent_name in INTENT_TYPES:
            keywords = INTENT_KEYWORDS.get(intent_name, ())
            if any(keyword in normalized for keyword in keywords):
                if intent_name == "status_inquiry":
                    return "status_inquiry"
                if intent_name == "complaint":
                    return "complaint"
                if intent_name == "document_request":
                    return "document_request"
                if intent_name == "correction_request":
                    return "correction_request"
                if intent_name == "enrollment":
                    return "enrollment"
                if intent_name == "general_assistance":
                    return "general_assistance"
                if intent_name == "update_request":
                    return "update_request"

        if context_target and session_state and session_state.get("intent_type") in {"update_request", "correction_request"}:
            return str(session_state.get("intent_type"))

        if re.search(r"\b(status|check|track|what is the status)\b", normalized):
            return "status_inquiry"

        if re.search(r"\b(help|assist|support)\b", normalized):
            return "general_assistance"

        if re.search(r"\bproblem|issue|complaint|grievance\b", normalized):
            return "complaint"

        if re.search(r"\bcorrect|correction|fix|amend\b", normalized):
            return "correction_request"

        if re.search(r"\bdocument|certificate|copy|form\b", normalized):
            return "document_request"

        if re.search(r"\b(enroll|enrol|registration|new aadhaar)\b", normalized):
            return "enrollment"

        if re.search(r"\b(update|change|modify)\b", normalized):
            return "update_request"

        return "general_assistance"

    def _classify_update_target(self, message: str, context_target: str | None, intent_type: str, conversation_history: list[str] | None = None) -> str | None:
        normalized = normalize_text(message)
        history_text = " ".join(conversation_history or [])
        history_normalized = normalize_text(history_text)

        if intent_type == "status_inquiry":
            return None

        if not normalized:
            return context_target or "unknown"

        matches: list[str] = []
        for target_name, keywords in UPDATE_TARGET_KEYWORDS.items():
            if any(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized) for keyword in keywords):
                if target_name in {"address", "mobile_number", "email", "name", "date_of_birth", "gender", "biometric"}:
                    matches.append(target_name)

        if matches:
            return matches[0]

        if context_target:
            return context_target

        if history_normalized:
            for target_name, keywords in UPDATE_TARGET_KEYWORDS.items():
                if any(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", history_normalized) for keyword in keywords):
                    if target_name in {"address", "mobile_number", "email", "name", "date_of_birth", "gender", "biometric"}:
                        return target_name

        if re.search(r"\bupdate\b|\bchange\b|\bmodify\b", normalized):
            return "unknown"

        if intent_type in {"update_request", "correction_request"}:
            return "unknown"
        return None

    def _extract_entities(self, message: str, update_type: str | None, context_target: str | None, session_state: dict[str, Any] | None) -> list[ExtractedEntity]:
        target = update_type or context_target
        extracted = [ExtractedEntity(**entity) for entity in extract_entities(message, previous_target=target, session_state=session_state)]
        if target and target != "unknown":
            matching = [entity for entity in extracted if entity.entity_type == target]
            if not matching and re.search(rf"\b{target.replace('_', ' ')}\b", normalize_text(message)):
                value = self._fallback_value_for_target(message, target)
                if value:
                    extracted.append(ExtractedEntity(entity_type=target, value=value, normalized_value=normalize_text(value), confidence=0.9, source_text=message))
        return extracted

    def _infer_intent_from_history(self, history_normalized: str) -> str | None:
        if not history_normalized:
            return None
        for intent_name in INTENT_TYPES:
            keywords = INTENT_KEYWORDS.get(intent_name, ())
            if any(keyword in history_normalized for keyword in keywords):
                return intent_name
        return None

    def _fallback_value_for_target(self, message: str, target: str) -> str | None:
        text = message
        if target == "address":
            return self._capture_after_keyword(text, "address")
        if target == "mobile_number":
            return self._capture_after_keyword(text, "mobile")
        if target == "email":
            return self._capture_after_keyword(text, "email")
        if target == "name":
            return self._capture_after_keyword(text, "name")
        if target == "date_of_birth":
            return self._capture_after_keyword(text, "date of birth")
        if target == "gender":
            return self._capture_after_keyword(text, "gender")
        return None

    def _capture_after_keyword(self, text: str, keyword: str) -> str | None:
        pattern = rf"{keyword}\s*(?:is|was|=|:)?\s*([A-Za-z0-9][A-Za-z0-9,\s./-]{{1,80}})"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        value = match.group(1).strip(" .;!?")
        if value and not value.lower().startswith(keyword.lower()):
            if keyword == "mobile":
                if re.search(r"\d", value):
                    return value
                return None
            return value
        return None

    def _identify_missing_information(self, intent_type: str, update_type: str | None, entities: list[ExtractedEntity], message: str) -> list[MissingInformation]:
        if not message.strip():
            return []

        if intent_type == "status_inquiry":
            return []

        if intent_type in {"update_request", "correction_request"}:
            if not update_type or update_type == "unknown":
                return [
                    MissingInformation(
                        field_name="update_type",
                        reason="The requested Aadhaar update target is not specified.",
                        required=True,
                        severity="medium",
                    )
                ]

            mapped = MISSING_FIELD_MAP.get(update_type)
            if mapped and not any(entity.entity_type == update_type for entity in entities):
                return [
                    MissingInformation(
                        field_name=mapped,
                        reason=f"The new {update_type.replace('_', ' ')} is not explicitly provided.",
                        required=True,
                        severity="medium",
                    )
                ]

        return []

    def _resolve_urgency(self, intent_type: str, update_type: str | None, normalized: str) -> str:
        if "urgent" in normalized or "immediate" in normalized or intent_type == "complaint":
            return "high"
        if intent_type in {"update_request", "correction_request"}:
            return "normal"
        return "low" if intent_type == "general_assistance" else "normal"

    def _calculate_confidence(self, intent_type: str, update_type: str | None, entities: list[ExtractedEntity], message: str, context_target: str | None) -> float:
        normalized = normalize_text(message)
        if not normalized:
            return 0.05

        score = 0.15
        if "aadhaar" in normalized:
            score += 0.2
        if intent_type != "general_assistance":
            score += 0.25
        if update_type and update_type != "unknown":
            score += 0.2
        if entities:
            score += 0.15
        if any(keyword in normalized for keyword in ("update", "change", "status", "problem", "correct", "help")):
            score += 0.15
        if intent_type in {"update_request", "correction_request"} and (update_type in (None, "unknown")):
            score -= 0.15
        if any(keyword in normalized for keyword in ("maybe", "perhaps", "i think", "likely")):
            score -= 0.1
        if context_target and update_type in (None, "unknown"):
            score -= 0.05
        return round(max(0.0, min(1.0, score)), 2)

    def _build_summary(self, intent_type: str, update_type: str | None) -> str:
        if intent_type == "status_inquiry":
            return "User wants to check the Aadhaar status."
        if intent_type == "update_request":
            if update_type and update_type != "unknown":
                return f"User wants to update Aadhaar {update_type.replace('_', ' ')}."
            return "User wants to update Aadhaar details."
        if intent_type == "correction_request":
            if update_type and update_type != "unknown":
                return f"User wants to correct Aadhaar {update_type.replace('_', ' ')}."
            return "User wants to correct Aadhaar details."
        if intent_type == "document_request":
            return "User is requesting an Aadhaar-related document."
        if intent_type == "complaint":
            return "User is raising an Aadhaar-related complaint."
        if intent_type == "enrollment":
            return "User is asking about Aadhaar enrollment."
        return "User needs general Aadhaar assistance."
