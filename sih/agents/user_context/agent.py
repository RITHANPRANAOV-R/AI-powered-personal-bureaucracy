"""User Context & Profile Agent: vault-scoped facts, never auto-confirmed."""

from __future__ import annotations

import re
from typing import Iterable, Optional

from pydantic import ValidationError

from agents.intent_understanding.schema import IntentResult

from .config import ProfileConfig, load_profile_config
from .files import (
    VaultAccessError,
    VaultDocument,
    excerpt_for_model,
    resolve_vault_dir,
    scan_vault,
)
from .llm import ProfileModelUnavailable, ProfileOllamaClient, extract_json_object
from .schema import (
    CONTRACT_VERSION,
    ConsentAction,
    ConsentUpdate,
    FactConflict,
    FactSourceType,
    FactStatus,
    ProcessingMode,
    ProfileContextRequest,
    ProfileContextResult,
    ProfileFact,
    ProfileStatus,
    Sensitivity,
    utc_now,
)
from .storage import ProfileStore, is_secret_key

LABELED_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_ /-]{1,40})\s*[:=]\s*(.+)$")

KEY_ALIASES = {
    "name": "full_name",
    "applicant_name": "full_name",
    "full name": "full_name",
    "dob": "date_of_birth",
    "date of birth": "date_of_birth",
    "birth_date": "date_of_birth",
    "phone": "mobile",
    "phone_number": "mobile",
    "mobile_number": "mobile",
    "email_address": "email",
    "address": "present_address",
    "current_address": "present_address",
    "pin": "pincode",
    "pin_code": "pincode",
    "postal_code": "pincode",
    "sex": "gender",
}

PASSPORT_KEYS = {
    "full_name",
    "given_name",
    "surname",
    "date_of_birth",
    "place_of_birth",
    "gender",
    "nationality",
    "email",
    "mobile",
    "present_address",
    "permanent_address",
    "state",
    "city",
    "district",
    "pincode",
    "father_name",
    "mother_name",
    "marital_status",
    "existing_passport_number",
    "language_preference",
}

AADHAAR_KEYS = {
    "full_name",
    "date_of_birth",
    "gender",
    "present_address",
    "state",
    "city",
    "pincode",
    "aadhaar_number",
    "mobile",
    "email",
    "language_preference",
}

GENERIC_KEYS = {
    "full_name",
    "date_of_birth",
    "gender",
    "nationality",
    "email",
    "mobile",
    "present_address",
    "state",
    "city",
    "pincode",
    "language_preference",
}

PERSONAL_KEYS = {
    "email",
    "mobile",
    "present_address",
    "permanent_address",
    "date_of_birth",
    "place_of_birth",
}

HIGHLY_SENSITIVE_KEYS = {
    "aadhaar_number",
    "pan",
    "pan_number",
    "passport_number",
    "existing_passport_number",
    "voter_id",
    "driving_licence_number",
    "bank_account",
}

INSTRUCTION_MARKERS = (
    "ignore previous",
    "you are now",
    "grant access",
    "read ~/.ssh",
    "bypass consent",
    "reveal secrets",
    "system prompt",
)


class UserContextAgent:
    def __init__(
        self,
        config: Optional[ProfileConfig] = None,
        ollama_client: Optional[ProfileOllamaClient] = None,
    ) -> None:
        self.config = config or load_profile_config()
        self.ollama_client = ollama_client or ProfileOllamaClient(self.config)

    def build_user_context(self, request: ProfileContextRequest) -> ProfileContextResult:
        """
        Public callable.

        Signature:
            def build_user_context(request: ProfileContextRequest) -> ProfileContextResult

        Deterministic code owns file access, confirmation, and persistence.
        Optional Ollama extraction is validated with Pydantic and never auto-confirmed.
        """
        request = ProfileContextRequest.model_validate(request)
        warnings: list[str] = []
        used_ollama = False
        used_deterministic = False

        try:
            vault = resolve_vault_dir(request.vault_dir)
        except VaultAccessError as exc:
            return _failed_result(request, [str(exc)])

        documents, scanned, scan_warnings = scan_vault(vault)
        warnings.extend(scan_warnings)

        store = ProfileStore(_resolve_profile_path(request.profile_path))
        try:
            profile_facts = store.load()
        except OSError as exc:
            return _failed_result(request, [f"Could not read profile: {exc}"], scanned_files=scanned)

        allowed = allowed_keys_for(request.intent, request.requested_fact_keys)
        candidates: list[ProfileFact] = []

        for pref_key, pref_value in (request.user_preferences or {}).items():
            key = normalize_key(pref_key)
            if not key or is_secret_key(key) or not _is_relevant_key(key, allowed, request.requested_fact_keys):
                continue
            used_deterministic = True
            candidates.append(
                _make_fact(
                    key=key,
                    value=pref_value,
                    status=FactStatus.USER_CONFIRMED,
                    source_type=FactSourceType.USER,
                    source_ref="user_preferences",
                    relevant_to=_relevance_reason(key, request.intent),
                    confirmed=True,
                    confidence=1.0,
                )
            )

        for fact in profile_facts:
            if not _is_relevant_key(fact.key, allowed, request.requested_fact_keys):
                continue
            used_deterministic = True
            source_ref = fact.source_ref
            if not source_ref.startswith("profile:"):
                source_ref = f"profile:{fact.key}"
            candidates.append(
                fact.model_copy(
                    update={
                        "source_type": FactSourceType.PROFILE,
                        "source_ref": source_ref,
                        "relevant_to": fact.relevant_to or _relevance_reason(fact.key, request.intent),
                    }
                )
            )

        for document in documents:
            labeled, remainder = parse_labeled_facts(document.text)
            used_deterministic = True
            for key, value in labeled.items():
                if is_secret_key(key):
                    warnings.append(f"Ignored secret-like field in {document.relative_path}.")
                    continue
                if not _is_relevant_key(key, allowed, request.requested_fact_keys):
                    continue
                candidates.append(
                    _make_fact(
                        key=key,
                        value=value,
                        status=FactStatus.DOCUMENT_EXTRACTED,
                        source_type=FactSourceType.DOCUMENT,
                        source_ref=document.relative_path,
                        relevant_to=_relevance_reason(key, request.intent),
                        confirmed=False,
                        confidence=0.72,
                    )
                )

            if request.allow_model_extraction and _looks_unstructured(remainder):
                extracted, model_warning = self._model_extract(request, document, remainder, allowed)
                if model_warning:
                    warnings.append(model_warning)
                if extracted:
                    used_ollama = True
                    candidates.extend(extracted)

        relevant, conflicts = merge_facts(candidates)
        missing = _missing_requested(request.requested_fact_keys, relevant)
        questions = _questions(request, missing, conflicts)
        status = _status(relevant, missing, conflicts, request.requested_fact_keys, scanned)

        if used_ollama and used_deterministic:
            mode = ProcessingMode.MIXED
        elif used_ollama:
            mode = ProcessingMode.OLLAMA
        else:
            mode = ProcessingMode.DETERMINISTIC
            if request.allow_model_extraction and any(_looks_unstructured(doc.text) for doc in documents) and not used_ollama:
                # Model was allowed but unused because labeled parse covered the file, or it failed.
                pass

        result = ProfileContextResult(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            intent_request_id=request.intent.request_id,
            service_name=request.intent.service_name,
            task_type=request.intent.task_type,
            jurisdiction=request.intent.jurisdiction,
            profile_status=status,
            relevant_facts=relevant,
            missing_requested_facts=missing,
            conflicts=conflicts,
            questions_for_user=questions,
            scanned_files=scanned,
            consent_updates=[],
            profile_updated=False,
            processing_mode=mode,
            warnings=warnings,
        )
        return ProfileContextResult.model_validate(result.model_dump())

    def apply_consent(
        self,
        request: ProfileContextRequest,
        result: ProfileContextResult,
        decisions: dict[str, ConsentAction],
        answers: dict[str, str],
    ) -> ProfileContextResult:
        """Apply CLI consent. Persistence happens only for explicit save actions."""
        store = ProfileStore(_resolve_profile_path(request.profile_path))
        now = utc_now()
        facts_by_key = {fact.key: fact for fact in result.relevant_facts}
        consent_updates: list[ConsentUpdate] = []
        to_persist: list[ProfileFact] = []

        for key, value in answers.items():
            if is_secret_key(key):
                result.warnings.append(f"Refused to accept secret-like key '{key}'.")
                continue
            fact = facts_by_key.get(key)
            action = decisions.get(key, ConsentAction.USE_ONCE)
            if fact:
                updated = fact.model_copy(
                    update={
                        "value": value,
                        "status": FactStatus.USER_CONFIRMED if action != ConsentAction.SKIP else fact.status,
                        "source_type": FactSourceType.USER,
                        "source_ref": "user_interview",
                        "confirmed_by_user": action != ConsentAction.SKIP,
                        "extracted_at": now,
                        "confidence": 1.0 if action != ConsentAction.SKIP else fact.confidence,
                    }
                )
            else:
                if action == ConsentAction.SKIP:
                    continue
                updated = _make_fact(
                    key=normalize_key(key),
                    value=value,
                    status=FactStatus.USER_CONFIRMED,
                    source_type=FactSourceType.USER,
                    source_ref="user_interview",
                    relevant_to=_relevance_reason(key, request.intent),
                    confirmed=True,
                    confidence=1.0,
                )
            facts_by_key[updated.key] = updated
            if action == ConsentAction.SAVE:
                to_persist.append(updated)
            consent_updates.append(
                ConsentUpdate(key=updated.key, action=action, persisted=action == ConsentAction.SAVE)
            )

        for key, action in decisions.items():
            if key in answers:
                continue
            fact = facts_by_key.get(key)
            if not fact:
                continue
            if action == ConsentAction.SKIP:
                facts_by_key.pop(key, None)
                consent_updates.append(ConsentUpdate(key=key, action=action, persisted=False))
                continue
            confirmed = action in {ConsentAction.SAVE, ConsentAction.USE_ONCE}
            updated = fact.model_copy(
                update={
                    "status": FactStatus.USER_CONFIRMED if confirmed else fact.status,
                    "confirmed_by_user": confirmed,
                    "source_type": FactSourceType.USER if confirmed else fact.source_type,
                    "source_ref": "user_interview" if confirmed else fact.source_ref,
                    "extracted_at": now,
                    "confidence": 1.0 if confirmed else fact.confidence,
                }
            )
            facts_by_key[key] = updated
            if action == ConsentAction.SAVE:
                to_persist.append(updated)
            consent_updates.append(
                ConsentUpdate(key=key, action=action, persisted=action == ConsentAction.SAVE)
            )

        profile_updated = False
        if request.save_confirmed_facts and to_persist:
            store.upsert_confirmed(to_persist)
            profile_updated = True
        elif to_persist and not request.save_confirmed_facts:
            result.warnings.append("Consented facts were not persisted because save_confirmed_facts is false.")
            consent_updates = [
                item.model_copy(update={"persisted": False}) if item.action == ConsentAction.SAVE else item
                for item in consent_updates
            ]

        relevant = list(facts_by_key.values())
        missing = _missing_requested(request.requested_fact_keys, relevant)
        _relevant, conflicts = merge_facts(relevant)
        status = _status(_relevant, missing, conflicts, request.requested_fact_keys, result.scanned_files)
        return result.model_copy(
            update={
                "relevant_facts": _relevant,
                "missing_requested_facts": missing,
                "conflicts": conflicts,
                "questions_for_user": _questions(request, missing, conflicts),
                "consent_updates": consent_updates,
                "profile_updated": profile_updated,
                "profile_status": status,
            }
        )

    def _model_extract(
        self,
        request: ProfileContextRequest,
        document: VaultDocument,
        remainder: str,
        allowed: set[str],
    ) -> tuple[list[ProfileFact], Optional[str]]:
        excerpt = excerpt_for_model(remainder)
        if _looks_like_instruction_injection(excerpt):
            excerpt = "[instruction-like text omitted]\n" + excerpt
        try:
            completion = self.ollama_client.extract_facts(
                service_name=request.intent.service_name,
                task_type=request.intent.task_type.value,
                jurisdiction=request.intent.jurisdiction,
                requested_keys=list(request.requested_fact_keys),
                allowed_keys=sorted(allowed),
                document_name=document.relative_path,
                excerpt=excerpt,
            )
            parsed = extract_json_object(completion.content)
        except (ProfileModelUnavailable, ValueError, TypeError) as exc:
            return [], f"Model extraction skipped ({document.relative_path}): {exc}. Deterministic parsing was used instead."

        facts: list[ProfileFact] = []
        for item in parsed.get("facts") or []:
            if not isinstance(item, dict):
                continue
            key = normalize_key(str(item.get("key") or ""))
            value = str(item.get("value") or "").strip()
            if not key or not value or is_secret_key(key):
                continue
            if not _is_relevant_key(key, allowed, request.requested_fact_keys):
                continue
            if not _value_supported_by_text(value, document.text):
                continue
            try:
                fact = _make_fact(
                    key=key,
                    value=value,
                    status=FactStatus.DOCUMENT_EXTRACTED,
                    source_type=FactSourceType.DOCUMENT,
                    source_ref=document.relative_path,
                    relevant_to=str(item.get("relevant_to") or _relevance_reason(key, request.intent)),
                    confirmed=False,
                    confidence=_bounded_confidence(item.get("confidence"), default=0.55),
                    sensitivity=_sensitivity_from(item.get("sensitivity"), key),
                )
            except (ValidationError, ValueError):
                continue
            facts.append(fact)
        return facts, None


_default_agent = UserContextAgent()


def build_user_context(request: ProfileContextRequest) -> ProfileContextResult:
    return _default_agent.build_user_context(request)


def parse_labeled_facts(text: str) -> tuple[dict[str, str], str]:
    found: dict[str, str] = {}
    leftover_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LABELED_LINE.match(stripped)
        if not match:
            leftover_lines.append(stripped)
            continue
        key = normalize_key(match.group(1))
        value = match.group(2).strip().strip("\"'")
        if not key or not value or is_secret_key(key):
            continue
        found[key] = value
    remainder = "\n".join(leftover_lines).strip()
    return found, remainder


def normalize_key(raw: str) -> str:
    lowered = re.sub(r"[\s\-]+", "_", raw.strip().lower())
    lowered = re.sub(r"[^a-z0-9_]", "", lowered)
    lowered = KEY_ALIASES.get(lowered.replace("_", " "), KEY_ALIASES.get(lowered, lowered))
    if lowered in KEY_ALIASES:
        lowered = KEY_ALIASES[lowered]
    return lowered


def allowed_keys_for(intent: IntentResult, requested: Iterable[str]) -> set[str]:
    keys = set(GENERIC_KEYS)
    service = (intent.service_name or "").lower()
    document = (intent.document_type or "").lower()
    blob = f"{service} {document} {intent.normalized_goal.lower()}"
    if "passport" in blob:
        keys |= PASSPORT_KEYS
    if "aadhaar" in blob or "aadhar" in blob:
        keys |= AADHAAR_KEYS
    keys.update(requested)
    for entity in intent.entities:
        mapped = normalize_key(entity.type)
        if mapped:
            keys.add(mapped)
    return keys


def merge_facts(facts: list[ProfileFact]) -> tuple[list[ProfileFact], list[FactConflict]]:
    grouped: dict[str, list[ProfileFact]] = {}
    for fact in facts:
        grouped.setdefault(fact.key, []).append(fact)

    merged: list[ProfileFact] = []
    conflicts: list[FactConflict] = []
    rank = {
        FactStatus.USER_CONFIRMED: 3,
        FactStatus.DOCUMENT_EXTRACTED: 2,
        FactStatus.INFERRED: 1,
        FactStatus.UNKNOWN: 0,
    }
    for key, items in grouped.items():
        unique_values = []
        for item in items:
            marker = item.value.strip().lower()
            if marker not in {value.value.strip().lower() for value in unique_values}:
                unique_values.append(item)
        if len(unique_values) > 1:
            conflicts.append(
                FactConflict(
                    key=key,
                    competing_values=[item.value for item in unique_values],
                    source_refs=[item.source_ref for item in unique_values],
                    note="Values disagree across sources. Not treated as confirmed.",
                )
            )
            for item in unique_values:
                if item.confirmed_by_user and item.status == FactStatus.USER_CONFIRMED:
                    merged.append(item)
            continue
        best = sorted(items, key=lambda item: (rank[item.status], item.confirmed_by_user), reverse=True)[0]
        merged.append(best)
    merged.sort(key=lambda item: item.key)
    return merged, conflicts


def mask_display_value(fact: ProfileFact) -> str:
    if fact.sensitivity == Sensitivity.ORDINARY:
        return fact.value
    value = fact.value
    if len(value) <= 4:
        return "****"
    return ("*" * max(4, len(value) - 4)) + value[-4:]


def _make_fact(
    *,
    key: str,
    value: str,
    status: FactStatus,
    source_type: FactSourceType,
    source_ref: str,
    relevant_to: str,
    confirmed: bool,
    confidence: float,
    sensitivity: Optional[Sensitivity] = None,
) -> ProfileFact:
    return ProfileFact(
        key=key,
        value=value.strip(),
        status=status,
        source_type=source_type,
        source_ref=source_ref,
        extracted_at=utc_now(),
        confidence=confidence,
        relevant_to=relevant_to,
        sensitivity=sensitivity or _sensitivity_for_key(key),
        confirmed_by_user=confirmed and status == FactStatus.USER_CONFIRMED,
    )


def _sensitivity_for_key(key: str) -> Sensitivity:
    if key in HIGHLY_SENSITIVE_KEYS:
        return Sensitivity.HIGHLY_SENSITIVE
    if key in PERSONAL_KEYS:
        return Sensitivity.PERSONAL
    return Sensitivity.ORDINARY


def _sensitivity_from(raw: object, key: str) -> Sensitivity:
    try:
        if raw:
            return Sensitivity(str(raw))
    except ValueError:
        pass
    return _sensitivity_for_key(key)


def _is_relevant_key(key: str, allowed: set[str], requested: Iterable[str]) -> bool:
    requested_set = set(requested)
    if requested_set:
        return key in requested_set or key in allowed
    return key in allowed


def _relevance_reason(key: str, intent: IntentResult) -> str:
    service = intent.service_name or "the current service"
    task = intent.task_type.value
    return f"May be relevant to {task} for {service}; not a verified government requirement."


def _usable_value(fact: ProfileFact) -> bool:
    return bool(fact.value.strip())


def _missing_requested(requested: list[str], facts: list[ProfileFact]) -> list[str]:
    return [
        key
        for key in requested
        if not any(fact.key == key and fact.confirmed_by_user and _usable_value(fact) for fact in facts)
    ]


def _looks_unstructured(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 40:
        return False
    labeled, remainder = parse_labeled_facts(stripped)
    return len(remainder) >= 40 and len(remainder.split()) >= 8


def _looks_like_instruction_injection(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in INSTRUCTION_MARKERS)


def _value_supported_by_text(value: str, source_text: str) -> bool:
    haystack = source_text.lower()
    needle = value.lower().strip()
    if needle in haystack:
        return True
    tokens = [token for token in re.split(r"[^\w]+", needle) if len(token) > 3]
    if not tokens:
        return False
    return sum(1 for token in tokens if token in haystack) >= max(1, len(tokens) // 2)


def _bounded_confidence(raw: object, default: float) -> float:
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _questions(
    request: ProfileContextRequest,
    missing: list[str],
    conflicts: list[FactConflict],
) -> list[str]:
    questions: list[str] = []
    for key in missing:
        questions.append(
            f"What is your {key.replace('_', ' ')}? Asked because it was listed in requested_fact_keys, not because an official rule was retrieved."
        )
    for conflict in conflicts:
        questions.append(
            f"Which {conflict.key.replace('_', ' ')} should be used? Sources: {', '.join(conflict.source_refs)}."
        )
    return questions


def _status(
    facts: list[ProfileFact],
    missing: list[str],
    conflicts: list[FactConflict],
    requested: list[str],
    scanned,
) -> ProfileStatus:
    if conflicts:
        return ProfileStatus.CONFLICTS_FOUND
    if missing:
        return ProfileStatus.NEEDS_USER_INPUT
    if not facts:
        return ProfileStatus.NO_RELEVANT_CONTEXT
    unread = [item for item in scanned if item.status.value in {"unreadable", "unsupported"}]
    confirmed = [fact for fact in facts if fact.confirmed_by_user]
    if unread and facts:
        return ProfileStatus.PARTIAL
    if requested and not all(
        any(fact.key == key and fact.confirmed_by_user for fact in facts) for key in requested
    ):
        return ProfileStatus.PARTIAL
    if not confirmed:
        return ProfileStatus.PARTIAL
    return ProfileStatus.READY


def _failed_result(
    request: ProfileContextRequest,
    warnings: list[str],
    scanned_files=None,
) -> ProfileContextResult:
    return ProfileContextResult(
        contract_version=CONTRACT_VERSION,
        request_id=request.request_id,
        intent_request_id=request.intent.request_id,
        service_name=request.intent.service_name,
        task_type=request.intent.task_type,
        jurisdiction=request.intent.jurisdiction,
        profile_status=ProfileStatus.FAILED,
        scanned_files=scanned_files or [],
        processing_mode=ProcessingMode.DETERMINISTIC,
        warnings=warnings,
    )


def _resolve_profile_path(path: str):
    from pathlib import Path

    return Path(path).expanduser().resolve()
