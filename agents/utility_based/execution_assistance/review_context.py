"""Single-process, restart-invalidated review authority. No I/O under its lock."""
from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import secrets
import threading
import time
from uuid import uuid4

from .schema import ConfirmedExecutionContext, ConfirmedFact
from .address_projection import eligible_post_office, project_confirmed_resolution, RESOLUTION_INPUT_KEYS


class ReviewError(ValueError):
    pass


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass
class ReviewRecord:
    verifier: bytes = field(repr=False)
    context: ConfirmedExecutionContext
    created: float
    expires: float
    revision: int = 0
    generation: int = 0
    lookup_status: str = "none"
    result: object = None
    published: dict | None = None
    confirmed: dict | None = None
    projected_fact: object = None
    publication_revision: int = 0
    revoked: bool = False
    handoff: str = "none"
    operation: str | None = None
    execution_uncertain: bool = False


class ReviewRegistry:
    def __init__(self, *, capacity=128, lifetime=1800, clock=time.monotonic):
        # Thirty minutes is prototype policy, not a government requirement.
        self.capacity, self.lifetime, self.clock = capacity, lifetime, clock
        self._records = {}
        self._lock = threading.RLock()

    def _get(self, context_id):
        if not isinstance(context_id, str):
            raise ReviewError("Invalid review context identifier.")
        record = self._records.get(context_id)
        if record is None or record.revoked or self.clock() >= record.expires:
            raise ReviewError("Review context is missing, expired or revoked. Confirm a new context.")
        return record

    def authenticate(self, context_id, secret, session_id=None):
        with self._lock:
            record = self._get(context_id)
            supplied = sha256((secret or "").encode()).digest()
            if not hmac.compare_digest(supplied, record.verifier):
                raise ReviewError("Review capability is missing or invalid.")
            if session_id is not None and session_id != record.context.session_id:
                raise ReviewError("Review capability does not authorize this execution session.")

    def create(self, context):
        with self._lock:
            now = self.clock()
            self._records = {k: v for k, v in self._records.items() if not v.revoked and now < v.expires}
            if len(self._records) >= self.capacity:
                raise ReviewError("Review capacity reached. Retry after an existing context expires.")
            if context.address_resolution or any(f.resolution_projection for f in context.facts.values()):
                raise ReviewError("Create a clean citizen-confirmed context before resolution.")
            if len(context.model_dump_json().encode()) > 1024 * 1024:
                raise ReviewError("Review input exceeds the prototype 1 MiB state limit.")
            context_id, secret = str(uuid4()), secrets.token_urlsafe(32)
            canonical = context.model_copy(deep=True, update={"session_id": "execution-" + str(uuid4()), "review_context": None})
            self._records[context_id] = ReviewRecord(sha256(secret.encode()).digest(), canonical, now, now + self.lifetime)
            return context_id, secret, self._snapshot(context_id)

    def _result_reference(self, context_id, record):
        return {"id": context_id, "input_revision": record.revision, "generation": record.generation,
                "result_binding": digest(record.result.model_dump(mode="json")) if record.result else None}

    def _reference(self, context_id, record):
        return {**self._result_reference(context_id, record),
                "publication_revision": record.publication_revision if record.published is not None else None}

    def _confirmation_bound(self, context_id, record, *, required=False):
        """Single authority check; callers hold the registry lock and use _get for expiry."""
        if record.confirmed is None:
            if required:
                raise ReviewError("Confirm the exact current publication or continue without projection.")
            return False
        expected = {**self._result_reference(context_id, record), "publication_revision": record.publication_revision}
        if (record.lookup_status != "completed" or record.result is None or record.published is None
                or digest(record.published) != digest(expected)
                or record.confirmed.get("action") != "confirm_post_office"
                or digest(record.confirmed.get("reference")) != digest(expected)):
            raise ReviewError("Confirmation does not match the exact current publication.")
        return True

    def _snapshot(self, context_id):
        record = self._get(context_id)
        context = record.context.model_copy(deep=True)
        if record.result is not None:
            context.facts["address_resolution"] = ConfirmedFact(value=record.result.model_copy(deep=True),
                provenance="postal_address_resolution_metadata", status="unconfirmed", allowed_for_execution=False)
            context = ConfirmedExecutionContext.model_validate(context.model_dump(mode="json"))
        if self._confirmation_bound(context_id, record):
            context = project_confirmed_resolution(context, explicitly_confirmed=True)
            # The projection timestamp must remain stable across snapshots.
            if getattr(record, "projected_fact", None) is not None:
                context.facts["post_office"] = record.projected_fact.model_copy(deep=True)
        context.review_context = self._reference(context_id, record)
        return context

    def snapshot(self, context_id):
        with self._lock:
            return self._snapshot(context_id)

    def validate(self, context, *, require_handoff=False):
        with self._lock:
            reference = context.review_context
            if not isinstance(reference, dict):
                raise ReviewError("Server-owned review reference is required.")
            context_id = reference.get("id")
            record = self._get(context_id)
            self._confirmation_bound(context_id, record)
            expected = self._snapshot(context_id)
            if digest(context.model_dump(mode="json")) != digest(expected.model_dump(mode="json")):
                raise ReviewError("Stale or substituted review execution context.")
            if require_handoff and record.handoff != "active":
                raise ReviewError("Review context has no active execution handoff.")
            return context_id

    def _idle(self, record):
        if record.operation is not None or record.handoff == "reserved":
            raise ReviewError("Review operation is pending; concurrent mutation is blocked.")

    def _invalidate(self, record):
        record.generation += 1
        record.result = record.published = record.confirmed = None
        record.lookup_status = "none"
        record.projected_fact = None

    def correct(self, context, corrections):
        from .context_validator import _apply_context_corrections
        with self._lock:
            context_id = self.validate(context)
            record = self._get(context_id)
            self._idle(record)
            corrected = _apply_context_corrections(context, corrections)
            relevant_change = any(context.facts.get(k) != corrected.facts.get(k) for k in RESOLUTION_INPUT_KEYS)
            canonical = corrected.model_copy(deep=True, update={"review_context": None})
            canonical.facts.pop("address_resolution", None)
            canonical.facts = {k: f for k, f in canonical.facts.items() if not f.resolution_projection}
            if len(canonical.model_dump_json().encode()) > 1024 * 1024:
                raise ReviewError("Corrected review input exceeds the prototype state limit.")
            if relevant_change:
                record.revision += 1
                self._invalidate(record)
            record.context = canonical
            return self._snapshot(context_id)

    def begin_lookup(self, context_id):
        with self._lock:
            record = self._get(context_id)
            self._idle(record)
            if record.handoff not in {"none", "active"}:
                raise ReviewError("A pending or uncertain handoff cannot resolve.")
            self._invalidate(record)
            record.lookup_status = "pending"
            return (record.revision, record.generation), record.context.model_copy(deep=True)

    def finish_lookup(self, context_id, reservation, result=None):
        with self._lock:
            record = self._get(context_id)
            if reservation != (record.revision, record.generation) or record.lookup_status != "pending":
                raise ReviewError("Lookup response belongs to an obsolete generation.")
            if result is None:
                record.lookup_status = "failed"
                return
            try:
                if len(result.model_dump_json().encode()) > 2 * 1024 * 1024:
                    raise ReviewError("Resolver result exceeds the prototype 2 MiB state limit.")
                # Validate structural consistency before retaining server resolver output.
                probe = record.context.model_copy(deep=True)
                probe.facts["address_resolution"] = ConfirmedFact(value=result, provenance="postal_address_resolution_metadata",
                    status="unconfirmed", allowed_for_execution=False)
                ConfirmedExecutionContext.model_validate(probe.model_dump(mode="json"))
                record.result = result.model_copy(deep=True)
                record.lookup_status = "completed"
            except BaseException:
                record.lookup_status = "failed"
                record.result = record.published = record.confirmed = record.projected_fact = None
                raise

    def fail_lookup(self, context_id, reservation):
        """Cleanup only its own pending generation; never replace newer authority."""
        with self._lock:
            record = self._records.get(context_id)
            if (record is not None and reservation == (record.revision, record.generation)
                    and record.lookup_status == "pending"):
                record.lookup_status = "failed"
                record.result = record.published = record.confirmed = record.projected_fact = None

    def publish(self, context_id):
        with self._lock:
            record = self._get(context_id)
            self._idle(record)
            if record.lookup_status != "completed" or record.result is None:
                raise ReviewError("A completed current server lookup is required before review.")
            expected = {**self._result_reference(context_id, record), "publication_revision": record.publication_revision}
            if record.published is None or digest(record.published) != digest(expected):
                record.publication_revision += 1
                record.confirmed = record.projected_fact = None
                record.published = {**self._result_reference(context_id, record), "publication_revision": record.publication_revision}
            return dict(record.published), self._snapshot(context_id)

    def confirm(self, context_id, reference, action):
        with self._lock:
            record = self._get(context_id)
            self._idle(record)
            if record.handoff not in {"none", "active"} or action != "confirm_post_office":
                raise ReviewError("A distinct pre-launch Post Office confirmation is required.")
            if (record.published is None or not isinstance(reference, dict) or digest(reference) != digest(record.published)
                    or digest(record.published) != digest(self._reference(context_id, record))):
                raise ReviewError("Confirm the exact current published review result.")
            context = self._snapshot(context_id)
            if eligible_post_office(context) is None or ("post_office" in context.facts and not context.facts["post_office"].resolution_projection):
                raise ReviewError("Current Post Office evidence is ineligible or ambiguous.")
            if record.confirmed is None:
                record.confirmed = {"reference": dict(reference), "action": action, "confirmed_at": self.clock()}
                projected = self._snapshot(context_id)
                record.projected_fact = projected.facts["post_office"].model_copy(deep=True)
            return self._snapshot(context_id)

    def without_projection(self, context_id):
        with self._lock:
            record = self._get(context_id)
            self._idle(record)
            if record.handoff not in {"none", "active"}:
                raise ReviewError("Execution handoff is pending or uncertain.")
            self._invalidate(record)
            return self._snapshot(context_id)

    def reserve_launch(self, context):
        with self._lock:
            context_id = self.validate(context)
            record = self._get(context_id)
            self._idle(record)
            if record.handoff != "none" or record.lookup_status == "pending":
                raise ReviewError("Duplicate, pending or replayed launch is blocked.")
            self._confirmation_bound(context_id, record, required=record.result is not None)
            record.handoff = "reserved"
            return context_id

    def finish_launch(self, context_id, success):
        with self._lock:
            record = self._get(context_id)
            if record.handoff != "reserved":
                raise ReviewError("Launch reservation is missing.")
            record.handoff = "active" if success else "uncertain"

    def begin_execution(self, context):
        with self._lock:
            context_id = self.validate(context, require_handoff=True)
            record = self._get(context_id)
            self._idle(record)
            if record.execution_uncertain:
                raise ReviewError("Prior execution is uncertain; human reconciliation is required.")
            if record.lookup_status == "pending":
                raise ReviewError("Complete the current review before execution.")
            self._confirmation_bound(context_id, record, required=record.result is not None)
            record.operation = "execution"
            return context_id

    def end_execution(self, context_id, *, uncertain=False):
        with self._lock:
            record = self._records.get(context_id)
            if record is not None:
                record.execution_uncertain = record.execution_uncertain or uncertain
                record.operation = None

    def revoke(self, context_id):
        with self._lock:
            record = self._get(context_id)
            self._idle(record)
            record.revoked = True
            self._invalidate(record)


review_registry = ReviewRegistry()
