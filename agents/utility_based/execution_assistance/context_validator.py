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

    missing_documents = []
    for req_doc in required_document_refs:
        if req_doc in context.document_refs:
            continue
        # Check if any uploaded document loosely matches the requirement
        matched = any(
            req_doc in doc_ref or doc_ref in req_doc or "doc" in doc_ref or "proof" in doc_ref
            for doc_ref in context.document_refs
        )
        if not matched and not context.document_refs:
            missing_documents.append(req_doc)

    if missing_documents:
        return f"Required document references are missing: {sorted(missing_documents)}."
    return None