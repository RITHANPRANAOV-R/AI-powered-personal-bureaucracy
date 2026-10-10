from .schema import ConfirmedExecutionContext, FactStatus


def validate_context(
    context: ConfirmedExecutionContext,
    required_fact_keys: list[str],
    required_document_refs: list[str],
) -> str | None:
    for key in required_fact_keys:
        fact = context.facts.get(key)
        if fact is None and f"existing_{key}" in context.facts:
            fact = context.facts.get(f"existing_{key}")
        if fact is None:
            return f"Required fact '{key}' is missing."
        if fact.status != FactStatus.CONFIRMED or not fact.allowed_for_execution:
            return f"Required fact '{key}' is not confirmed and allowed for execution."
        if not fact.provenance.strip():
            return f"Required fact '{key}' has no provenance."

    if required_document_refs and not context.document_refs:
        return f"Required document references are missing: {sorted(required_document_refs)}."
    if len(context.document_refs) != len(set(context.document_refs)):
        return "Duplicate document references are not allowed."
    unknown = set(context.document_refs) - context.known_document_ids
    if unknown:
        return f"Unresolved document references: {sorted(unknown)}."
    missing = set(required_document_refs) - set(context.document_refs)
    if missing:
        return f"Required document references are missing: {sorted(missing)}."
    return None


def apply_context_corrections(context: ConfirmedExecutionContext, corrections: dict) -> ConfirmedExecutionContext:
    if context.review_context is not None:
        from .review_context import review_registry
        return review_registry.correct(context, corrections)
    return _apply_context_corrections(context, corrections)


def normalize_address_corrections(corrections: dict) -> dict:
    """Citizen-input aliases normalize before confirmation; never rewrite bound contexts."""
    if not isinstance(corrections, dict) or any(not isinstance(key, str) for key in corrections):
        raise ValueError("Corrections must be a mapping with string keys.")
    edits = dict(corrections)
    for alias, canonical in (("address", "new_address"), ("pin", "pincode"),
                             ("postal_code", "pincode"), ("postalCode", "pincode")):
        if alias not in edits:
            continue
        value = edits.pop(alias)
        if isinstance(value, str):
            value = value.strip()
        previous = edits.get(canonical)
        if isinstance(previous, str):
            previous = previous.strip()
        if previous and value and previous != value:
            raise ValueError(f"Conflicting corrections for '{canonical}'.")
        if value or canonical not in edits:
            edits[canonical] = value
    return edits


def _apply_context_corrections(context: ConfirmedExecutionContext, corrections: dict) -> ConfirmedExecutionContext:
    """Apply explicit citizen edits upstream of the protected browser implementation."""
    import re
    from .schema import ConfirmedFact

    if not isinstance(corrections, dict) or any(not isinstance(key, str) for key in corrections):
        raise ValueError("Corrections must be a mapping with string keys.")
    if {key.casefold() for key in corrections} & {"review_capability", "capability", "authorization", "review_context", "resolution_projection", "address_resolution"}:
        raise ValueError("Review credentials and resolver authority cannot be corrected as citizen facts.")
    edits = {key: value for key, value in corrections.items() if "otp" not in key.casefold() and value}
    for key, value in edits.items():
        if not isinstance(value, str):
            raise ValueError(f"Correction for '{key}' must be a string.")
    edits = {key: value.strip() for key, value in edits.items() if value.strip()}
    edits = normalize_address_corrections(edits)
    if "pincode" in edits and re.fullmatch(r"[1-9][0-9]{5}", edits["pincode"]) is None:
        raise ValueError("Corrected PIN must be exactly six digits beginning with 1-9.")
    facts = {key: fact.model_copy(deep=True) for key, fact in context.facts.items()}
    changed = {key for key, value in edits.items()
               if key not in facts or facts[key].value != value or facts[key].resolution_projection is not None}
    relevant = {"address", "new_address", "existing_address", "pincode", "state", "district", "post_office", "po", "vtc", "city", "town", "locality", "area", "sector", "house_no", "house", "building", "flat", "street", "road", "lane", "landmark", "care_of"}
    if changed & relevant:
        facts.pop("address_resolution", None)
        facts = {key: fact for key, fact in facts.items()
                 if fact.resolution_projection is None and fact.provenance != "address_resolution_confirmed"}
    for key in changed:
        previous = facts.get(key)
        facts[key] = ConfirmedFact(value=edits[key], provenance="user_corrected",
                                   status=FactStatus.CONFIRMED, allowed_for_execution=True,
                                   source_document_id=previous.source_document_id if previous else None)
    if "new_address" in edits:
        facts["address"] = facts["new_address"].model_copy(deep=True)
    return ConfirmedExecutionContext(session_id=context.session_id, application_id=context.application_id,
                                     document_refs=list(context.document_refs), facts=facts)


def reconstruct_execution_context(raw: dict, *, capability: str | None = None) -> ConfirmedExecutionContext:
    """Preserve canonical facts/provenance across JSON; missing permission fails closed."""
    import re
    if raw.get("review_context") is not None:
        from .review_context import review_registry
        reference = raw["review_context"]
        if not isinstance(reference, dict):
            raise ValueError("Invalid review reference.")
        review_registry.authenticate(reference.get("id"), capability, raw.get("session_id"))
        supplied = ConfirmedExecutionContext.model_validate(raw)
        review_registry.validate(supplied)
        return review_registry.snapshot(reference["id"])
    if any(isinstance(f, dict) and (f.get("resolution_projection") is not None or f.get("provenance") == "address_resolution_confirmed")
           for f in raw.get("facts", {}).values()):
        raise ValueError("Server-owned review reference is required for resolver projection.")
    facts = {}
    for key, value in raw.get("facts", {}).items():
        facts[key] = value if isinstance(value, dict) else {
            "value": value, "provenance": "user-input", "status": "unconfirmed", "allowed_for_execution": False,
        }
    context = ConfirmedExecutionContext(session_id=raw.get("session_id") or "browser-session",
                                         application_id=raw.get("application_id"),
                                         facts=facts, document_refs=raw.get("document_refs", []))
    pin = context.facts.get("pincode")
    if pin is not None and (not isinstance(pin.value, str) or re.fullmatch(r"[1-9][0-9]{5}", pin.value) is None):
        raise ValueError("Canonical PIN must be a six-digit string beginning with 1-9.")
    error = validate_context(context, [], [])
    if error:
        raise ValueError(error)
    return context
