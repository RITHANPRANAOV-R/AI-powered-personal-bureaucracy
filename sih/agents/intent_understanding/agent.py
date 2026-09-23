"""Intent Understanding Agent: public callable, Ollama path, and labeled fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import ValidationError

from .config import AgentConfig, load_config
from .llm import OllamaClient, OllamaUnavailableError, extract_json_object
from .schema import (
    CONTRACT_VERSION,
    Complexity,
    EntitySource,
    IntentRequest,
    IntentResult,
    IntentStatus,
    SourcedEntity,
    SourcedStatement,
    TaskType,
)

ExecutionMode = Literal["ollama_local", "deterministic_fallback"]

_EXPLICIT_URGENCY = re.compile(
    r"\b(urgent|urgently|asap|emergency|tatkal|immediate|immediately|today|tonight|deadline)\b",
    re.IGNORECASE,
)

# Copied only when the exact phrase appears in caller-supplied text. Not inferred from the host machine.
_EXPLICIT_JURISDICTIONS = (
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Jammu and Kashmir",
    "Jammu & Kashmir",
    "Andaman and Nicobar",
    "Dadra and Nagar Haveli",
    "Daman and Diu",
    "Lakshadweep",
    "Puducherry",
    "Chandigarh",
    "Ladakh",
    "Delhi",
    "New Delhi",
    "India",
)


@dataclass(frozen=True)
class IntentRun:
    """CLI/debug wrapper. Downstream agents must use `result` only."""

    result: IntentResult
    execution_mode: ExecutionMode
    fallback_reason: Optional[str] = None


class IntentUnderstandingAgent:
    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        ollama_client: Optional[OllamaClient] = None,
        prefer_ollama: bool = True,
    ) -> None:
        self.config = config or load_config()
        self.ollama_client = ollama_client or OllamaClient(self.config)
        self.prefer_ollama = prefer_ollama
        self.last_run: Optional[IntentRun] = None

    def understand_intent(self, request: IntentRequest) -> IntentResult:
        """
        Public callable.

        Signature:
            def understand_intent(request: IntentRequest) -> IntentResult

        Always returns a Pydantic-validated IntentResult. Model JSON is never trusted raw.
        """
        run = self.understand_intent_with_meta(request)
        return run.result

    def understand_intent_with_meta(self, request: IntentRequest) -> IntentRun:
        request = IntentRequest.model_validate(request)
        fallback_reason: Optional[str] = None

        if self.prefer_ollama:
            try:
                completion = self.ollama_client.complete_json(
                    request.model_dump(mode="json")
                )
                parsed = extract_json_object(completion.content)
                result = assemble_intent_result(request, parsed)
                run = IntentRun(result=result, execution_mode="ollama_local", fallback_reason=None)
                self.last_run = run
                return run
            except (OllamaUnavailableError, ValueError, TypeError, ValidationError) as exc:
                fallback_reason = str(exc)

        parsed = deterministic_intent_payload(request)
        result = assemble_intent_result(request, parsed)
        if fallback_reason is None:
            fallback_reason = "Ollama path was not used."
        run = IntentRun(
            result=result,
            execution_mode="deterministic_fallback",
            fallback_reason=fallback_reason,
        )
        self.last_run = run
        return run


_default_agent = IntentUnderstandingAgent()


def understand_intent(request: IntentRequest) -> IntentResult:
    """Module-level public callable used by later orchestrators."""
    return _default_agent.understand_intent(request)


def assemble_intent_result(request: IntentRequest, parsed: dict[str, Any]) -> IntentResult:
    """Validate model/fallback JSON and enforce request-grounded fields."""
    language = request.language_preference or _optional_str(parsed.get("language")) or "English"

    candidate = {
        "contract_version": request.contract_version or CONTRACT_VERSION,
        "request_id": request.request_id,
        "original_goal": request.user_goal,
        "normalized_goal": _optional_str(parsed.get("normalized_goal")) or _normalize_goal(request.user_goal),
        "service_name": parsed.get("service_name"),
        "document_type": parsed.get("document_type"),
        "task_type": parsed.get("task_type") or TaskType.UNKNOWN.value,
        "jurisdiction": parsed.get("jurisdiction"),
        "entities": parsed.get("entities") or [],
        "stated_facts": _coerce_stated_facts(parsed.get("stated_facts")),
        "assumptions": _string_list(parsed.get("assumptions")),
        "ambiguities": _string_list(parsed.get("ambiguities")),
        "clarification_questions": _string_list(parsed.get("clarification_questions")),
        "language": language,
        "urgency": parsed.get("urgency"),
        "complexity": parsed.get("complexity") or Complexity.UNKNOWN.value,
        "confidence": parsed.get("confidence", 0.0),
        "status": parsed.get("status") or IntentStatus.NEEDS_CLARIFICATION.value,
    }

    result = IntentResult.model_validate(candidate)
    result = apply_grounding_guards(request, result)
    return IntentResult.model_validate(result.model_dump())


def apply_grounding_guards(request: IntentRequest, result: IntentResult) -> IntentResult:
    combined_text = _combined_request_text(request)

    jurisdiction = result.jurisdiction
    if jurisdiction and not _value_supported(jurisdiction, combined_text):
        jurisdiction = None

    if not jurisdiction:
        jurisdiction = _explicit_jurisdiction(request)

    urgency = result.urgency
    if urgency and not _explicit_urgency_present(combined_text):
        urgency = None
    elif not urgency and _explicit_urgency_present(combined_text):
        # Keep model null if it did not copy the stated word; still record only if explicit.
        match = _EXPLICIT_URGENCY.search(combined_text)
        urgency = match.group(1) if match else None

    entities = [
        entity
        for entity in result.entities
        if _value_supported(entity.value, _source_text(request, entity.source))
    ]
    if jurisdiction and not any(entity.type.lower() == "location" for entity in entities):
        loc_source = (
            EntitySource.USER_GOAL
            if jurisdiction.lower() in request.user_goal.lower()
            else EntitySource.USER_CONTEXT
        )
        if _value_supported(jurisdiction, _source_text(request, loc_source)):
            entities.append(SourcedEntity(type="location", value=jurisdiction, source=loc_source))
    stated_facts = [
        fact
        for fact in result.stated_facts
        if _statement_supported(fact.text, _source_text(request, fact.source))
    ]

    status = result.status
    questions = list(result.clarification_questions)
    ambiguities = list(result.ambiguities)
    confidence = float(result.confidence)
    service_known = bool(result.service_name)

    if status != IntentStatus.UNABLE_TO_CLASSIFY:
        if not service_known or result.task_type == TaskType.UNKNOWN:
            status = IntentStatus.NEEDS_CLARIFICATION
            if not questions:
                questions = _default_clarifying_questions(result)
            if not service_known and "Which government service or document this is about" not in " ".join(ambiguities):
                ambiguities.append("Service or document type is not identified.")
            if result.task_type == TaskType.UNKNOWN:
                ambiguities.append("Task type is not identified.")
        elif questions and status == IntentStatus.READY:
            # Non-blocking assumptions may remain; questions imply clarification.
            status = IntentStatus.NEEDS_CLARIFICATION

    if status == IntentStatus.READY:
        questions = []
        confidence = max(confidence, 0.55)
    elif status == IntentStatus.NEEDS_CLARIFICATION:
        confidence = min(confidence, 0.55)
        if not questions:
            questions = _default_clarifying_questions(result)
    else:
        confidence = min(confidence, 0.2)

    return result.model_copy(
        update={
            "contract_version": request.contract_version or CONTRACT_VERSION,
            "request_id": request.request_id,
            "original_goal": request.user_goal,
            "jurisdiction": jurisdiction,
            "urgency": urgency,
            "entities": entities,
            "stated_facts": stated_facts,
            "ambiguities": _dedupe(ambiguities),
            "clarification_questions": _dedupe(questions),
            "status": status,
            "confidence": round(min(max(confidence, 0.0), 1.0), 3),
            "language": request.language_preference or result.language or "English",
        }
    )


def deterministic_intent_payload(request: IntentRequest) -> dict[str, Any]:
    """
    Labeled heuristic fallback. This is not an LLM.
    Used when Ollama is unavailable or the model output cannot be parsed.
    """
    text = _combined_request_text(request).lower()
    goal = request.user_goal.lower()

    service_name, document_type = _match_service(text)
    task_type = _match_task(goal)
    if task_type == TaskType.UNKNOWN:
        task_type = _match_task(text)
    entities: list[dict[str, str]] = []
    facts: list[dict[str, str]] = []

    if "passport" in request.user_goal.lower() or "passport" in text:
        entities.append({"type": "service", "value": "passport", "source": EntitySource.USER_GOAL.value})
        facts.append({"text": "User mentioned passport.", "source": EntitySource.USER_GOAL.value})
    elif service_name:
        entities.append({"type": "service", "value": service_name, "source": EntitySource.USER_GOAL.value})
    if document_type:
        entities.append({"type": "document", "value": document_type, "source": EntitySource.USER_GOAL.value})
    extracted_jurisdiction = _explicit_jurisdiction(request)
    if extracted_jurisdiction:
        entities.append(
            {
                "type": "location",
                "value": extracted_jurisdiction,
                "source": EntitySource.USER_GOAL.value
                if extracted_jurisdiction.lower() in request.user_goal.lower()
                else EntitySource.USER_CONTEXT.value,
            }
        )
        facts.append(
            {
                "text": extracted_jurisdiction,
                "source": EntitySource.USER_GOAL.value
                if extracted_jurisdiction.lower() in request.user_goal.lower()
                else EntitySource.USER_CONTEXT.value,
            }
        )
    elif request.jurisdiction_hint:
        location_source = (
            EntitySource.USER_GOAL.value
            if request.jurisdiction_hint.lower() in request.user_goal.lower()
            else EntitySource.USER_CONTEXT.value
        )
        # jurisdiction_hint is caller-supplied; treat it as user_goal provenance when not in context text.
        if request.jurisdiction_hint.lower() not in (request.user_context or "").lower():
            location_source = EntitySource.USER_GOAL.value
        entities.append(
            {
                "type": "location",
                "value": request.jurisdiction_hint,
                "source": location_source,
            }
        )
        facts.append(
            {
                "text": request.jurisdiction_hint,
                "source": location_source,
            }
        )

    ambiguities: list[str] = []
    assumptions: list[str] = []
    questions: list[str] = []

    if not service_name:
        ambiguities.append("Service or document type is not identified.")
        questions.append("Which government service or document is this about (for example passport, Aadhaar, driving licence)?")
    if task_type == TaskType.UNKNOWN:
        ambiguities.append("Task type is not identified.")
        questions.append("What do you need to do: register, apply, renew, reissue, update details, or track status?")

    if "update my document" in goal or (task_type == TaskType.UPDATE and not service_name):
        assumptions.append("This might be an update to an existing government ID, but the document is unspecified.")

    if service_name and task_type != TaskType.UNKNOWN:
        status = IntentStatus.READY
        questions = []
        confidence = 0.74 if extracted_jurisdiction else 0.7
        complexity = Complexity.MEDIUM
        if task_type in {TaskType.TRACK, TaskType.UNDERSTAND_REQUIREMENTS}:
            complexity = Complexity.LOW
            confidence = 0.78
        elif task_type in {TaskType.REISSUE, TaskType.REGISTER}:
            complexity = Complexity.HIGH if task_type == TaskType.REISSUE else Complexity.MEDIUM
    elif not service_name and task_type == TaskType.UNKNOWN:
        status = IntentStatus.UNABLE_TO_CLASSIFY if len(request.user_goal.split()) <= 2 else IntentStatus.NEEDS_CLARIFICATION
        confidence = 0.15 if status == IntentStatus.UNABLE_TO_CLASSIFY else 0.28
        complexity = Complexity.UNKNOWN
    else:
        status = IntentStatus.NEEDS_CLARIFICATION
        confidence = 0.34
        complexity = Complexity.UNKNOWN

    urgency = None
    match = _EXPLICIT_URGENCY.search(_combined_request_text(request))
    if match:
        urgency = match.group(1)

    return {
        "normalized_goal": _normalize_goal(request.user_goal),
        "service_name": service_name,
        "document_type": document_type,
        "task_type": task_type.value,
        "jurisdiction": extracted_jurisdiction,
        "entities": entities,
        "stated_facts": facts,
        "assumptions": assumptions,
        "ambiguities": ambiguities,
        "clarification_questions": questions,
        "language": request.language_preference or "English",
        "urgency": urgency,
        "complexity": complexity.value,
        "confidence": confidence,
        "status": status.value,
    }


def _explicit_jurisdiction(request: IntentRequest) -> Optional[str]:
    if request.jurisdiction_hint:
        return request.jurisdiction_hint
    combined = _combined_request_text(request)
    for name in sorted(_EXPLICIT_JURISDICTIONS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", combined, flags=re.IGNORECASE):
            return name
    return None


def _match_service(text: str) -> tuple[Optional[str], Optional[str]]:
    if "passport" in text or "passport seva" in text:
        return "Passport Seva", "Passport"
    if "aadhaar" in text or "aadhar" in text or "uidai" in text:
        return "Aadhaar", "Aadhaar"
    if "driving licence" in text or "driving license" in text or re.search(r"\bdl\b", text):
        return "Driving Licence", "Driving Licence"
    if "voter" in text or "epic" in text:
        return "Voter Services", "Voter ID"
    if "pan card" in text or re.search(r"\bpan\b", text):
        return "PAN", "PAN Card"
    if "community certificate" in text or "caste certificate" in text:
        return "Community Certificate", "Community Certificate"
    return None, None


def _match_task(text: str) -> TaskType:
    if any(token in text for token in ("register", "registration", "sign up", "new user", "create account")):
        return TaskType.REGISTER
    if any(token in text for token in ("reissue", "lost", "stolen", "damaged", "replace")):
        return TaskType.REISSUE
    if "renew" in text:
        return TaskType.RENEW
    if any(token in text for token in ("track", "status", "file number", "application number")):
        return TaskType.TRACK
    if any(token in text for token in ("requirement", "documents needed", "eligibility", "how do i", "what do i need")):
        return TaskType.UNDERSTAND_REQUIREMENTS
    if any(token in text for token in ("update", "change address", "correct", "modify")):
        return TaskType.UPDATE
    if any(token in text for token in ("apply", "application", "fresh", "new passport", "first time")):
        return TaskType.APPLY
    return TaskType.UNKNOWN


def _default_clarifying_questions(result: IntentResult) -> list[str]:
    questions: list[str] = []
    if not result.service_name:
        questions.append(
            "Which government service or document is this about (for example passport, Aadhaar, driving licence)?"
        )
    if result.task_type in {TaskType.UNKNOWN, TaskType.OTHER}:
        questions.append(
            "What do you need to do: register, apply, renew, reissue, update details, or track status?"
        )
    return questions


def _combined_request_text(request: IntentRequest) -> str:
    parts = [
        request.user_goal,
        request.language_preference or "",
        request.jurisdiction_hint or "",
        request.user_context,
        request.conversation_context,
        " ".join(request.document_context),
    ]
    return "\n".join(part for part in parts if part)


def _source_text(request: IntentRequest, source: EntitySource) -> str:
    if source == EntitySource.USER_GOAL:
        return " ".join(
            part
            for part in (request.user_goal, request.jurisdiction_hint or "", request.language_preference or "")
            if part
        )
    if source == EntitySource.USER_CONTEXT:
        return " ".join(
            part for part in (request.user_context, request.jurisdiction_hint or "") if part
        )
    if source == EntitySource.DOCUMENT_CONTEXT:
        return " ".join(request.document_context)
    return request.conversation_context


_STOPWORDS = {
    "user",
    "mentioned",
    "stated",
    "as",
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "to",
    "of",
    "in",
}


def _value_supported(value: str, source_text: str) -> bool:
    if not value or not source_text:
        return False
    haystack = source_text.lower()
    needle = value.lower().strip()
    if needle in haystack:
        return True
    tokens = [token for token in re.split(r"[^\w]+", needle) if len(token) > 2 and token not in _STOPWORDS]
    if not tokens:
        return False
    return any(token.lower() in haystack for token in tokens)


def _statement_supported(statement: str, source_text: str) -> bool:
    if not source_text:
        return False
    if _value_supported(statement, source_text):
        return True
    tokens = [
        token
        for token in re.split(r"[^\w]+", statement.lower())
        if len(token) > 3 and token not in _STOPWORDS
    ]
    if not tokens:
        return False
    overlap = sum(1 for token in tokens if token in source_text.lower())
    return overlap >= 1


def _explicit_urgency_present(text: str) -> bool:
    return bool(_EXPLICIT_URGENCY.search(text))


def _normalize_goal(goal: str) -> str:
    compact = re.sub(r"\s+", " ", goal).strip()
    if compact.endswith("."):
        return compact
    return compact


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "unknown", "n/a"}:
        return None
    return text


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    items: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = item.get("text") or item.get("value") or ""
            if str(text).strip():
                items.append(str(text).strip())
        elif str(item).strip():
            items.append(str(item).strip())
    return items


def _coerce_stated_facts(value: Any) -> list[dict[str, str]]:
    if not value:
        return []
    facts: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            facts.append({"text": item.strip(), "source": EntitySource.USER_GOAL.value})
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("value") or item.get("fact") or "").strip()
            source = item.get("source") or EntitySource.USER_GOAL.value
            if text:
                facts.append({"text": text, "source": source})
    return facts


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return out
