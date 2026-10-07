"""Deterministic PIN-anchored postal resolution inside Information Retrieval.

Accepts existing UserDocument/Aadhaar field models or a component dictionary.
No LLM, execution handoff, browser interaction, or implicit citizen approval.
"""
from collections.abc import Mapping
import json
import re
from typing import Any

from pydantic import BaseModel

from ..live_retrieval.india_post_fetcher import (
    IndiaPostLocationFetcher, OGD_RESOURCE_ID, OGD_URL, PostalLookupResult,
    PostalLookupStatus,
)
from ..schemas.address_resolution import (
    AddressFieldStatus, AddressResolutionField, AddressResolutionResult,
    AddressResolutionStatus,
)
from ..schemas.evidence import Evidence, GroundingStatus
from ..schemas.retrieval_result import ConflictItem
from ..schemas.source import Source, SourceType
from ..schemas.user_document import UserDocument
from .query_builder import QueryNormalizer

# Component aliases only; no geographic substitutions or invented abbreviations.
CONTEXT_KEYS = {
    "state", "state_name", "statename", "district", "districtname",
    "post_office", "office_name", "officename", "po", "taluka",
    "pincode", "pin", "vtc", "city", "town", "village", "locality", "area",
    "new_address", "address", "existing_address", "house", "house_no",
    "building", "street", "road", "landmark",
}
CONSTRAINTS = {
    "state": (("state", "state_name", "statename"), "state_name"),
    "district": (("district", "districtname"), "district"),
    "post_office": (("post_office", "office_name", "officename", "po"), "office_name"),
    "taluka": (("taluka",), "taluka"),
}


class PostalAddressResolver:
    def __init__(self, fetcher: IndiaPostLocationFetcher | None = None):
        # Instantiate lazily so resolving an existing lookup has no HTTP/OCR side effects.
        self.fetcher = fetcher
        self.normalizer = QueryNormalizer()

    def _normalize(self, value: str) -> str:
        return self.normalizer.normalize(value.casefold().replace("-", " ").replace("_", " "))

    def resolve(
        self,
        pin: str,
        address_context: UserDocument | BaseModel | Mapping[str, Any] | None = None,
        postal_lookup: PostalLookupResult | None = None,
    ) -> AddressResolutionResult:
        context, document_id, context_timestamp = self._context(address_context)
        result = AddressResolutionResult(status=AddressResolutionStatus.INVALID_PIN, context=context)
        if not isinstance(pin, str) or re.fullmatch(r"[1-9][0-9]{5}", pin) is None:
            result.error_message = "PIN must be a six-digit string beginning with 1-9."
            return result
        result.queried_pin = pin
        self._context_evidence(result, document_id, context_timestamp)
        self._preserve_vtc(result)
        if postal_lookup is None:
            postal_lookup = (self.fetcher or IndiaPostLocationFetcher()).lookup(pin)
        lookup = postal_lookup.model_copy(deep=True)
        result.source = lookup.source
        result.source_resource_id = lookup.source_resource_id
        result.retrieved_at = lookup.retrieved_at
        result.lookup_status = lookup.status
        result.candidates = lookup.records

        successful = {PostalLookupStatus.SUCCESS, PostalLookupStatus.MULTIPLE_RECORDS, PostalLookupStatus.EMPTY_RESULT}
        if lookup.status not in successful:
            result.status = (AddressResolutionStatus.INVALID_PIN if lookup.status == PostalLookupStatus.INVALID_PIN
                             else AddressResolutionStatus.UNAVAILABLE)
            result.error_message = "Postal lookup did not return usable official data."
            return result
        if (lookup.source.url != OGD_URL or lookup.source.domain != "india_post"
                or lookup.source_resource_id != OGD_RESOURCE_ID or not lookup.retrieved_at):
            result.status = AddressResolutionStatus.UNAVAILABLE
            result.error_message = "Official postal source provenance is missing or inconsistent."
            return result
        if lookup.queried_pin != pin or any(r.pincode != pin for r in lookup.records):
            self._conflict(result, "pincode", "Postal lookup records or queried PIN differ from the requested PIN.")
            result.status = AddressResolutionStatus.CONFLICT
            return result
        if not lookup.records:
            result.status = AddressResolutionStatus.NO_RESULT
            return result
        if lookup.status == PostalLookupStatus.EMPTY_RESULT:
            result.status = AddressResolutionStatus.UNAVAILABLE
            result.error_message = "Postal lookup status and candidate records are inconsistent."
            return result

        for index, record in enumerate(result.candidates):
            result.evidence.append(Evidence(
                evidence_id=f"postal-{pin}-{index}",
                claim="Official postal record for the queried PIN; not UIDAI VTC evidence.",
                passage=json.dumps(record.source_record or record.model_dump(exclude={"source_record"}),
                                   sort_keys=True, ensure_ascii=False),
                source=lookup.source, retrieved_at=lookup.retrieved_at,
                grounding_status=GroundingStatus.VERIFIED_GROUNDED,
                metadata={"value_origin": "authoritative_postal", "queried_pin": pin,
                          "resource_id": lookup.source_resource_id, "candidate_index": index},
            ))

        for key in ("pincode", "pin"):
            supplied = self._value(context.get(key))
            if supplied and supplied != pin:
                self._conflict(result, "pincode", "Supplied address PIN contradicts the requested postal PIN.")
        plausible = set(range(len(result.candidates)))
        constrained_topics = []
        for topic, (aliases, attribute) in CONSTRAINTS.items():
            for key in aliases:
                supplied = self._value(context.get(key))
                if not supplied:
                    continue
                constrained_topics.append(topic)
                compatible = {i for i, record in enumerate(result.candidates)
                              if not getattr(record, attribute)
                              or self._normalize(getattr(record, attribute)) == self._normalize(supplied)}
                if not compatible:
                    self._conflict(result, topic, f"Supplied {key} contradicts every published candidate {topic} value.")
                if plausible & compatible != plausible:
                    result.narrowing_evidence_ids.append(f"context-{key}")
                plausible &= compatible
        if not plausible and not result.conflicts:
            self._conflict(result, "address_context", "Supplied postal components cannot describe any one candidate together.")

        if result.conflicts:
            result.status = AddressResolutionStatus.CONFLICT
            result.plausible_candidate_indexes = sorted(plausible) if not any(c.topic == "pincode" for c in result.conflicts) else []
            conflict_topics = {c.topic for c in result.conflicts}
            if "address_context" in conflict_topics or "pincode" in conflict_topics:
                conflict_topics.update(constrained_topics if "pincode" not in conflict_topics else CONSTRAINTS)
            for topic in ("state", "district", "post_office"):
                field = self._postal_field(result, list(range(len(result.candidates))), CONSTRAINTS[topic][1])
                if topic in conflict_topics:
                    field.status, field.value = AddressFieldStatus.CONFLICT, None
                setattr(result, topic, field)
            return result

        # Locality/city and free-text matches are hints, not assertions that the
        # directory enumerates every locality. An unmatched hint is never a conflict.
        hint_sets = []
        for key in ("locality", "area", "city", "town", "village"):
            supplied = self._value(context.get(key))
            if supplied:
                matches = self._location_matches(result, supplied, phrase=False)
                if matches:
                    hint_sets.append((key, matches))
        address = next((self._value(context.get(k)) for k in ("new_address", "address", "existing_address")
                        if self._value(context.get(k))), "")
        if address:
            matches = self._location_matches(result, address, phrase=True)
            if matches:
                hint_sets.append((next(k for k in ("new_address", "address", "existing_address") if self._value(context.get(k))), matches))
        narrowed = plausible.copy()
        hint_evidence_ids = []
        for key, matches in hint_sets:
            # Missing published location fields cannot eliminate a candidate.
            unknown = {i for i in plausible if not result.candidates[i].office_name
                       and not result.candidates[i].taluka}
            next_narrowed = narrowed & (matches | unknown)
            if next_narrowed != narrowed:
                hint_evidence_ids.append(f"context-{key}")
            narrowed = next_narrowed
        if not narrowed:
            result.ambiguity_information.append("Contextual location hints do not support one consistent candidate; candidates retained.")
        else:
            plausible = narrowed
            result.narrowing_evidence_ids.extend(hint_evidence_ids)
        result.plausible_candidate_indexes = sorted(plausible)
        for topic in ("state", "district", "post_office"):
            setattr(result, topic, self._postal_field(result, sorted(plausible), CONSTRAINTS[topic][1]))
        complete = all(getattr(result, k).status == AddressFieldStatus.RESOLVED
                       for k in ("state", "district", "post_office"))
        result.status = AddressResolutionStatus.RESOLVED if complete and narrowed else AddressResolutionStatus.AMBIGUOUS
        if result.status == AddressResolutionStatus.AMBIGUOUS:
            result.ambiguity_information.append("Postal fields or office choice remain ambiguous or incomplete; no candidate was selected automatically.")
        return result

    def _postal_field(self, result, indexes, attribute):
        values = [getattr(result.candidates[i], attribute) for i in indexes]
        groups = {}
        for value in values:
            if value and self._normalize(value):
                groups.setdefault(self._normalize(value), []).append(value)
        options = [sorted(set(groups[key]))[0] for key in sorted(groups)]
        resolved = len(options) == 1 and all(values)
        return AddressResolutionField(
            value=options[0] if resolved else None,
            status=(AddressFieldStatus.RESOLVED if resolved else
                    AddressFieldStatus.AMBIGUOUS if options else AddressFieldStatus.UNRESOLVED),
            options=options, value_origin="authoritative_postal" if options else None,
            supporting_candidate_indexes=[i for i in indexes if getattr(result.candidates[i], attribute)],
            evidence_ids=[f"postal-{result.queried_pin}-{i}" for i in indexes if getattr(result.candidates[i], attribute)] + result.narrowing_evidence_ids,
        )

    def _location_matches(self, result, text, phrase):
        normalized = self._normalize(text)
        return {i for i, record in enumerate(result.candidates)
                if any(value and self._normalize(value) and
                       (f" {self._normalize(value)} " in f" {normalized} " if phrase
                        else self._normalize(value) == normalized)
                       for value in (record.office_name, record.taluka))}

    @staticmethod
    def _value(item):
        if isinstance(item, dict):
            item = item.get("value")
        return item.strip() if isinstance(item, str) else ""

    @staticmethod
    def _context(context):
        document_id = None
        timestamp = ""
        if isinstance(context, UserDocument):
            document_id, timestamp = context.document_id, context.processing_timestamp
            raw = context.extracted_fields
        elif isinstance(context, BaseModel):
            document_id = getattr(context, "document_id", None)
            raw = {k: getattr(context, k) for k in type(context).model_fields}
        else:
            raw = dict(context or {})
        values = {}
        for key in sorted(CONTEXT_KEYS & raw.keys()):
            item = raw[key]
            if isinstance(item, BaseModel):
                item = item.model_dump(mode="json")
            if isinstance(item, Mapping):
                # Copy only established field provenance, not arbitrary fact metadata.
                item = {k: item[k] for k in ("value", "confidence", "page_number", "source_region",
                        "source_document_id", "provenance", "confirmed_at") if k in item}
            values[key] = json.loads(json.dumps(item, ensure_ascii=False))
        return values, document_id, timestamp

    def _context_evidence(self, result, document_id, timestamp):
        for key, item in result.context.items():
            value = self._value(item)
            if not value:
                continue
            metadata = item if isinstance(item, dict) else {}
            source_id = metadata.get("source_document_id") or document_id
            source = Source(
                source_id=source_id or "supplied-address-context",
                authority="User/document context", domain="address_context",
                source_type=SourceType.USER_DOCUMENT if source_id else SourceType.OTHER,
                trust_level=0.0, last_checked=metadata.get("confirmed_at") or timestamp,
                freshness_policy=None,
            )
            result.evidence.append(Evidence(
                evidence_id=f"context-{key}", claim=f"Supplied address component: {key}",
                passage=value, source=source,
                retrieved_at=metadata.get("confirmed_at") or timestamp,
                confidence=metadata.get("confidence", 0.0),
                grounding_status=GroundingStatus.UNVERIFIED,
                page_number=metadata.get("page_number"),
                metadata={"value_origin": "user_document_context", "context_field": key,
                          "original_field": metadata},
            ))

    def _preserve_vtc(self, result):
        value = self._value(result.context.get("vtc"))
        if value:
            result.vtc = AddressResolutionField(
                value=value, status=AddressFieldStatus.UNRESOLVED, options=[value],
                value_origin="user_document_context", evidence_ids=["context-vtc"],
            )
        result.ambiguity_information.append("VTC requires UIDAI-side resolution or user confirmation; postal Taluka/Office is not UIDAI VTC evidence.")

    @staticmethod
    def _conflict(result, topic, description):
        result.conflicts.append(ConflictItem(
            conflict_id=f"address-conflict-{topic}-{len(result.conflicts)}",
            topic=topic, description=description,
            sources=[result.source] if result.source else [],
            evidence_list=list(result.evidence),
        ))
