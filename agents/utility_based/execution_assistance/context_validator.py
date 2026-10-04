from .schema import ConfirmedExecutionContext, FactStatus


def validate_context(
    context: ConfirmedExecutionContext,
    required_fact_keys: list[str],
    required_document_refs: list[str],
) -> str | None:
    for key in required_fact_keys:
        fact = context.facts.get(key)
        if fact is None:
            return f"Required fact '{key}' is missing."
        if fact.status != FactStatus.CONFIRMED or not fact.allowed_for_execution:
            return f"Required fact '{key}' is not confirmed and allowed for execution."
        if not fact.provenance.strip():
            return f"Required fact '{key}' has no provenance."

    missing_documents = set(required_document_refs) - set(context.document_refs)
    if missing_documents:
        return f"Required document references are missing: {sorted(missing_documents)}."
    return None