from __future__ import annotations

from datetime import datetime
import uuid

from .extractor import extract_entities, extract_signals
from .schemas import ExtractedEntity, IntentEvent, IntentRequest, IntentResult, MissingInformation


class IntentUnderstandingService:
    def process(self, request: IntentRequest) -> IntentResult:
        user_message = (request.user_message or "").strip()
        intent_signals, update_signals, entities, urgency = extract_signals(user_message)

        intent_type = self._classify_intent(intent_signals, user_message)
        update_type = self._classify_update_type(update_signals, user_message)
        summary = self._build_summary(intent_type, update_type)
        missing_information = self._identify_missing_information(intent_type, update_type, user_message)
        confidence = self._calculate_confidence(intent_type, update_type, entities, user_message)

        result = IntentResult(
            session_id=request.session_id,
            intent_type=intent_type,
            update_type=update_type,
            summary=summary,
            entities=entities,
            urgency=urgency,
            missing_information=missing_information,
            confidence=confidence,
        )

        self._emit_event(result)
        return result

    def _classify_intent(self, intent_signals: list[str], user_message: str) -> str:
        normalized = user_message.lower().strip()
        if not normalized:
            return "general_assistance"

        if "status" in normalized and ("check" in normalized or "status" in normalized):
            return "status_inquiry"
        if "complaint" in normalized or "problem" in normalized or "grievance" in normalized:
            return "complaint"
        if "document" in normalized or "certificate" in normalized or "copy" in normalized:
            return "document_request"
        if "enroll" in normalized or "enrol" in normalized or "registration" in normalized:
            return "enrollment"
        if "update" in normalized or "change" in normalized or "modify" in normalized or "correct" in normalized:
            return "update"
        if "help" in normalized or "assistance" in normalized or "support" in normalized:
            return "general_assistance"
        if "aadhaar" in normalized:
            return "general_assistance"
        return "general_assistance"

    def _classify_update_type(self, update_signals: list[str], user_message: str) -> str | None:
        normalized = user_message.lower().strip()
        if not normalized:
            return None
        if "address" in normalized and "address" in [*update_signals, "address"]:
            return "address"
        if any(token in normalized for token in ["mobile", "phone number"]):
            return "mobile_number"
        if "email" in normalized or "e-mail" in normalized:
            return "email"
        if "name" in normalized and "update" in normalized:
            return "name"
        if "date of birth" in normalized or "dob" in normalized:
            return "date_of_birth"
        if "gender" in normalized:
            return "gender"
        if "biometric" in normalized or "fingerprint" in normalized or "iris" in normalized:
            return "biometric"
        if update_signals:
            return update_signals[0]
        return None

    def _build_summary(self, intent_type: str, update_type: str | None) -> str:
        if intent_type == "status_inquiry":
            return "User wants to check the Aadhaar update status."
        if intent_type == "update" and update_type:
            return f"User wants to update Aadhaar {update_type.replace('_', ' ')}."
        if intent_type == "general_assistance":
            return "User needs general Aadhaar assistance."
        if intent_type == "enrollment":
            return "User is asking about Aadhaar enrollment."
        if intent_type == "document_request":
            return "User is requesting an Aadhaar-related document."
        if intent_type == "complaint":
            return "User is raising an Aadhaar-related complaint."
        return "User is interacting with an Aadhaar-related workflow."

    def _identify_missing_information(self, intent_type: str, update_type: str | None, user_message: str) -> list[MissingInformation]:
        if not user_message.strip():
            return [
                MissingInformation(
                    field_name="user_message",
                    reason="No user message was provided.",
                    required=True,
                    severity="high",
                )
            ]
        if intent_type == "update" and update_type is None:
            return [
                MissingInformation(
                    field_name="update_type",
                    reason="The requested Aadhaar update target is not specified.",
                    required=True,
                    severity="medium",
                )
            ]
        return []

    def _calculate_confidence(
        self,
        intent_type: str,
        update_type: str | None,
        entities: list[ExtractedEntity],
        user_message: str,
    ) -> float:
        normalized = user_message.lower().strip()
        score = 0.4
        if "aadhaar" in normalized:
            score += 0.25
        if intent_type != "general_assistance":
            score += 0.2
        if update_type is not None:
            score += 0.15
        if entities:
            score += 0.1
        if not normalized:
            score = 0.1
        return max(0.0, min(1.0, score))

    def _emit_event(self, result: IntentResult) -> IntentEvent:
        event = IntentEvent(
            event_id=str(uuid.uuid4()),
            session_id=result.session_id,
            event_type="intent_understood",
            intent=result.intent_type,
            timestamp=datetime.utcnow(),
            source_agent="intent_understanding",
        )
        return event
