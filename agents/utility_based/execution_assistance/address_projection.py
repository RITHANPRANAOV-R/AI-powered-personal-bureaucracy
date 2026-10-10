"""Explicit upstream projection; no resolver/browser calls or implicit approval."""
from datetime import datetime, timezone
import hashlib
import json
import re
from agents.knowledge_based.information_retrieval.live_retrieval.india_post_fetcher import OGD_RESOURCE_ID, OGD_URL, PostalLookupStatus
from agents.knowledge_based.information_retrieval.schemas.address_resolution import AddressFieldStatus, AddressResolutionStatus
from agents.knowledge_based.information_retrieval.schemas.evidence import GroundingStatus
from .schema import ConfirmedExecutionContext, ConfirmedFact, FactStatus

PROJECTION_PROVENANCE = "address_resolution_confirmed"
RESOLUTION_INPUT_KEYS = frozenset({"pincode", "new_address", "address", "existing_address", "state", "district", "post_office", "po", "vtc", "city", "town", "locality", "area", "sector", "house_no", "house", "building", "flat", "street", "road", "lane", "landmark", "care_of"})


def _normalized(value):
    if isinstance(value, dict):
        value = value.get("value")
    return " ".join(value.casefold().split()) if isinstance(value, str) else ""


def projection_binding(context):
    result = context.address_resolution
    payload = {"resolution": result.model_dump(mode="json") if result else None,
               "inputs": {key: fact.model_dump(mode="json") for key, fact in context.facts.items()
                          if key in RESOLUTION_INPUT_KEYS and fact.resolution_projection is None}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def eligible_post_office(context):
    """Validate coherent official evidence, unique PO and current citizen inputs."""
    result = context.address_resolution
    pin = context.facts.get("pincode")
    if result is None or result.status != AddressResolutionStatus.RESOLVED or result.conflicts:
        return None
    if pin is None or pin.status != FactStatus.CONFIRMED or not pin.allowed_for_execution:
        return None
    if not isinstance(pin.value, str) or re.fullmatch(r"[1-9][0-9]{5}", pin.value) is None:
        return None
    if result.queried_pin != pin.value or not result.candidates or any(record.pincode != pin.value for record in result.candidates):
        return None
    if (result.source is None or result.source.url != OGD_URL or result.source.domain != "india_post"
            or result.source_resource_id != OGD_RESOURCE_ID or not result.retrieved_at
            or result.lookup_status not in {PostalLookupStatus.SUCCESS, PostalLookupStatus.MULTIPLE_RECORDS}):
        return None
    # Missing address/PIN context cannot establish that a result belongs to this request.
    for key in ("pincode", "new_address", "existing_address"):
        fact = context.facts.get(key)
        if fact is not None and _normalized(fact.value) != _normalized(result.context.get(key)):
            return None
    for key in RESOLUTION_INPUT_KEYS - {"pincode", "new_address", "existing_address", "address"}:
        fact = context.facts.get(key)
        if fact is not None and fact.resolution_projection is None and key in result.context:
            if _normalized(fact.value) != _normalized(result.context[key]):
                return None
    for key in ("state", "district"):
        fact = context.facts.get(key)
        if fact is not None and _normalized(fact.value) != _normalized(getattr(result, key).value):
            return None
    field = result.post_office
    target = _normalized(field.value)
    if field.status != AddressFieldStatus.RESOLVED or field.value_origin != "authoritative_postal" or not target:
        return None
    if {_normalized(option) for option in field.options} != {target}:
        return None
    indexes = result.plausible_candidate_indexes
    if not indexes or len(indexes) != len(set(indexes)) or any(type(i) is not int or i < 0 or i >= len(result.candidates) for i in indexes):
        return None
    if set(field.supporting_candidate_indexes) != set(indexes) or any(_normalized(result.candidates[i].office_name) != target for i in indexes):
        return None
    evidence = {item.evidence_id: item for item in result.evidence}
    if not field.evidence_ids or any(key not in evidence for key in field.evidence_ids):
        return None
    for index in indexes:
        item = evidence.get(f"postal-{pin.value}-{index}")
        if (item is None or item.evidence_id not in field.evidence_ids
                or item.grounding_status != GroundingStatus.VERIFIED_GROUNDED
                or item.source.url != OGD_URL or item.source.domain != "india_post"
                or item.retrieved_at != result.retrieved_at
                or item.metadata.get("resource_id") != OGD_RESOURCE_ID
                or item.metadata.get("queried_pin") != pin.value
                or item.metadata.get("candidate_index") != index):
            return None
        record = result.candidates[index]
        raw = record.source_record or record.model_dump(exclude={"source_record"})
        try:
            if json.loads(item.passage) != raw:
                return None
        except (ValueError, TypeError):
            return None
        normalized_record = {re.sub(r"[\s_-]", "", key.casefold()): value for key, value in raw.items()}
        raw_office = normalized_record.get("officename", normalized_record.get("office"))
        if str(normalized_record.get("pincode")) != pin.value or _normalized(raw_office) != target:
            return None
    for key in ("post_office", "po"):
        fact = context.facts.get(key)
        if fact is not None and fact.resolution_projection is None and _normalized(fact.value) != target:
            return None
    return field.value


def validate_projection(context):
    """Reject derived facts that outlive their evidence or confirmed address inputs."""
    for key, fact in context.facts.items():
        if fact.resolution_projection is None and fact.provenance != PROJECTION_PROVENANCE:
            continue
        metadata = fact.resolution_projection or {}
        expected = eligible_post_office(context)
        if (key != "post_office" or expected is None or fact.value != expected
                or fact.provenance != PROJECTION_PROVENANCE
                or fact.status != FactStatus.CONFIRMED or not fact.allowed_for_execution
                or metadata.get("explicitly_confirmed") is not True
                or metadata.get("eligible") is not True or metadata.get("field") != key
                or not metadata.get("confirmed_at")
                or metadata.get("binding") != projection_binding(context)
                or metadata.get("evidence_ids") != context.address_resolution.post_office.evidence_ids):
            raise ValueError("Stale, inconsistent or unconfirmed resolver projection.")


def project_confirmed_resolution(context: ConfirmedExecutionContext, *, explicitly_confirmed: bool = False) -> ConfirmedExecutionContext:
    """Opt-in PO scalar; retain PIN, addresses and the non-executable envelope.

    VTC is not projected: the existing resolver never establishes independently
    confirmed VTC. State/District have no active browser consumers.
    """
    result = ConfirmedExecutionContext.model_validate(context.model_dump(mode="json"))
    if explicitly_confirmed is not True:
        return result
    value = eligible_post_office(result)
    if value is None:
        return result
    existing = result.facts.get("post_office")
    if existing is not None and existing.resolution_projection is None:
        return result  # Preserve citizen facts even when they agree.
    result.facts["post_office"] = ConfirmedFact(
        value=value, provenance=PROJECTION_PROVENANCE, status=FactStatus.CONFIRMED, allowed_for_execution=True,
        resolution_projection={"field": "post_office", "explicitly_confirmed": True, "eligible": True,
                               "confirmed_at": datetime.now(timezone.utc).isoformat(),
                               "binding": projection_binding(result),
                               "evidence_ids": list(result.address_resolution.post_office.evidence_ids)},
    )
    return ConfirmedExecutionContext.model_validate(result.model_dump(mode="json"))
