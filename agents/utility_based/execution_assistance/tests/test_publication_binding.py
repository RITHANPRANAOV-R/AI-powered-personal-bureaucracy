"""B.3.9 publication invariants; synthetic resolver evidence and mocked actions."""
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import AsyncMock, Mock
import pytest
from fastapi.testclient import TestClient
from agents.utility_based.execution_assistance.tests.test_review_context import setup, resolve, confirmed, result_for
from agents.utility_based.execution_assistance.review_context import ReviewError, digest
from agents.utility_based.execution_assistance.context_validator import reconstruct_execution_context, apply_context_corrections
from agents.utility_based.execution_assistance.interactive_session import InteractivePortalManager, ActiveBrowserSession, PortalStage
from agents.utility_based.execution_assistance.schema import ActionExecutionResult


def changed_result(context):
    from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver
    from agents.knowledge_based.information_retrieval.tests.test_address_resolver import lookup, postal_record
    pin = context.facts["pincode"].value
    return PostalAddressResolver().resolve(pin, {key: fact.value for key, fact in context.facts.items()},
        lookup([postal_record(pincode=pin)], queried_pin=pin, retrieved_at="2026-10-09T12:00:00+00:00"))


def replacement(registry, context_id):
    reservation, inputs = registry.begin_lookup(context_id)
    result = changed_result(inputs)
    registry.finish_lookup(context_id, reservation, result)
    return registry.publish(context_id)


def test_unchanged_reads_preserve_reference_confirmation_and_projection(monkeypatch):
    registry, cid, _, _ = setup(monkeypatch)
    context = confirmed(registry, cid)
    previous = copy.deepcopy(registry._records[cid].confirmed)
    for _ in range(3):
        reference, current = registry.publish(cid)
        assert reference == context.review_context
        assert current == context
        assert registry._records[cid].confirmed == previous
    assert context.facts["pincode"].value == "641025"
    assert context.facts["post_office"].value == "Alpha Office"


def test_replacement_lookup_requires_distinct_confirmation_and_reconfirmation(monkeypatch):
    registry, cid, _, _ = setup(monkeypatch)
    old = confirmed(registry, cid)
    reference, current = replacement(registry, cid)
    record = registry._records[cid]
    assert reference["publication_revision"] > old.review_context["publication_revision"]
    assert reference["result_binding"] != old.review_context["result_binding"]
    assert record.confirmed is None and record.projected_fact is None
    assert "post_office" not in current.facts
    with pytest.raises(ReviewError): registry.reserve_launch(current)
    with pytest.raises(ReviewError): registry.confirm(cid, old.review_context, "confirm_post_office")
    fresh = registry.confirm(cid, reference, "confirm_post_office")
    assert record.confirmed["reference"] == reference == fresh.review_context
    assert fresh.facts["post_office"].value == "Alpha Office"
    assert fresh.facts["pincode"].value == "641025"
    assert all(key not in fresh.facts for key in ["state", "district", "vtc", "locality"])


def test_publish_itself_atomically_clears_confirmation_when_result_binding_changes(monkeypatch):
    registry, cid, _, _ = setup(monkeypatch)
    context = confirmed(registry, cid)
    # Simulate a changed retained server result to exercise publish's own defensive invalidation.
    record = registry._records[cid]
    record.result = changed_result(record.context)
    reference, snapshot = registry.publish(cid)
    assert reference != context.review_context
    assert record.confirmed is None and record.projected_fact is None
    assert "post_office" not in snapshot.facts
    with pytest.raises(ReviewError): registry.reserve_launch(snapshot)
    assert registry.confirm(cid, reference, "confirm_post_office").facts["post_office"].value == "Alpha Office"


@pytest.mark.parametrize("boundary", ["snapshot", "validate", "reconstruction", "launch", "execution", "dispatch"])
def test_mismatched_confirmation_rejected_at_every_boundary(monkeypatch, boundary):
    registry, cid, secret, _ = setup(monkeypatch)
    context = confirmed(registry, cid)
    registry.reserve_launch(context); registry.finish_launch(cid, True)
    registry._records[cid].confirmed["reference"]["publication_revision"] += 1
    manager = InteractivePortalManager()
    session = ActiveBrowserSession(context.session_id, context)
    session.active_attempt = "reserved"
    session.attempts["reserved"] = {"state": "reserved"}
    calls = {"snapshot": lambda: registry.snapshot(cid), "validate": lambda: registry.validate(context),
        "reconstruction": lambda: reconstruct_execution_context(context.model_dump(mode="json"), capability=secret),
        "launch": lambda: registry.reserve_launch(context), "execution": lambda: registry.begin_execution(context),
        "dispatch": lambda: manager._mark_dispatch(session)}
    with pytest.raises(ReviewError, match="Confirmation"):
        calls[boundary]()
    assert session.attempts["reserved"]["state"] == "reserved"


@pytest.mark.parametrize("field", ["input_revision", "generation", "result_binding", "publication_revision"])
def test_complete_reference_cannot_be_substituted(monkeypatch, field):
    registry, cid, secret, _ = setup(monkeypatch)
    reference, context = resolve(registry, cid)
    fake = {**reference, field: "fabricated"}
    with pytest.raises(ReviewError): registry.confirm(cid, fake, "confirm_post_office")
    raw = context.model_dump(mode="json"); raw["review_context"] = fake
    with pytest.raises(ReviewError): reconstruct_execution_context(raw, capability=secret)


def test_old_publication_cannot_reconstruct_launch_execute_or_dispatch(monkeypatch):
    registry, cid, secret, _ = setup(monkeypatch)
    old = confirmed(registry, cid)
    registry.reserve_launch(old); registry.finish_launch(cid, True)
    replacement(registry, cid)
    for operation in [lambda: reconstruct_execution_context(old.model_dump(mode="json"), capability=secret),
        lambda: registry.reserve_launch(old), lambda: registry.begin_execution(old)]:
        with pytest.raises(ReviewError): operation()
    manager = InteractivePortalManager()
    session = ActiveBrowserSession(old.session_id, old)
    session.active_attempt = "reserved"; session.attempts["reserved"] = {"state": "reserved"}
    with pytest.raises(ReviewError): manager._mark_dispatch(session)


@pytest.mark.parametrize("operation", ["continue", "cancel", "expiry", "correction"])
def test_invalidation_cannot_preserve_usable_confirmation(monkeypatch, operation):
    now = [0]
    registry, cid, secret, _ = setup(monkeypatch, clock=lambda: now[0], lifetime=10)
    old = confirmed(registry, cid)
    if operation == "continue": registry.without_projection(cid)
    elif operation == "cancel": registry.revoke(cid)
    elif operation == "expiry": now[0] = 10
    else: apply_context_corrections(old, {"pincode": "560001"})
    with pytest.raises(ReviewError): registry.confirm(cid, old.review_context, "confirm_post_office")
    with pytest.raises(ReviewError): reconstruct_execution_context(old.model_dump(mode="json"), capability=secret)
    with pytest.raises(ReviewError): registry.reserve_launch(old)


def test_concurrent_replacement_and_confirmation_never_keep_old_binding(monkeypatch):
    registry, cid, _, _ = setup(monkeypatch)
    reference, _ = resolve(registry, cid)
    barrier = Barrier(2)
    def confirm_old():
        barrier.wait(timeout=2)
        try: registry.confirm(cid, reference, "confirm_post_office")
        except ReviewError: pass
    def replace():
        barrier.wait(timeout=2)
        return replacement(registry, cid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(confirm_old), pool.submit(replace)
        first.result(timeout=5); current, _ = second.result(timeout=5)
    assert registry._records[cid].confirmed is None
    assert registry.confirm(cid, current, "confirm_post_office").review_context == current


@pytest.mark.parametrize("first", ["confirm", "publish"])
def test_both_unchanged_publication_confirmation_orderings_preserve_binding(monkeypatch, first):
    registry, cid, _, _ = setup(monkeypatch)
    reference, _ = resolve(registry, cid)
    if first == "confirm": registry.confirm(cid, reference, "confirm_post_office")
    repeated, _ = registry.publish(cid)
    registry.confirm(cid, repeated, "confirm_post_office")
    assert repeated == reference == registry._records[cid].confirmed["reference"]


def test_expiry_during_authentication_inspection_prevents_dispatch(monkeypatch):
    now = [0]
    registry, cid, _, _ = setup(monkeypatch, clock=lambda: now[0], lifetime=10)
    context = confirmed(registry, cid)
    registry.reserve_launch(context); registry.finish_launch(cid, True)
    manager = InteractivePortalManager()
    session = ActiveBrowserSession(context.session_id, context, current_stage=PortalStage.STAGE_2_SERVICE)
    manager._sessions[session.session_id] = session
    manager._check_authentication_continuity = Mock(return_value=None)
    async def inspection(_):
        await asyncio.sleep(0)
        now[0] = 10
        return ActionExecutionResult(status="VERIFIED_SUCCESS", message="Synthetic inspection", verification_evidence="Synthetic dashboard")
    manager._verify_authentication = inspection
    manager._execute_stage_action_on_portal = AsyncMock()
    result = asyncio.run(manager.submit_step(session.session_id, True, request_id="expiry", expected_stage=session.current_stage.value, expected_state_version=0))
    manager._execute_stage_action_on_portal.assert_not_awaited()
    assert not result["is_completed"]
    assert session.attempts["expiry"]["state"] == "uncertain"


def test_api_review_pairs_reference_with_its_atomic_result_snapshot(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    registry, cid, secret, _ = setup(monkeypatch)
    original = registry.publish
    reservation, inputs = registry.begin_lookup(cid)
    registry.finish_lookup(cid, reservation, result_for(inputs))
    def raced_publish(context_id):
        reference, snapshot = original(context_id)
        reservation, inputs = registry.begin_lookup(context_id)
        registry.finish_lookup(context_id, reservation, changed_result(inputs))
        original(context_id)
        return reference, snapshot
    monkeypatch.setattr(registry, "publish", raced_publish)
    import importlib
    api = importlib.import_module("api.app")
    response = TestClient(api.create_app(document_service=Mock())).get("/api/review-contexts/" + cid + "/review", headers={"Authorization": "Bearer " + secret})
    assert response.status_code == 200
    body = response.json()
    assert body["review_reference"] == body["confirmed_context"]["review_context"]
    assert body["review_reference"]["result_binding"] == digest(body["confirmed_data"]["address_resolution"])
    assert body["review_reference"] != registry.snapshot(cid).review_context
    with pytest.raises(ReviewError): registry.confirm(cid, body["review_reference"], "confirm_post_office")


@pytest.mark.parametrize("field,value", [("publication_revision", True), ("input_revision", False), ("generation", True)])
def test_typed_reference_cannot_substitute_boolean_for_revision(monkeypatch, field, value):
    registry, cid, secret, _ = setup(monkeypatch)
    context = confirmed(registry, cid)
    raw = context.model_dump(mode="json")
    raw["review_context"][field] = value
    with pytest.raises(ReviewError): reconstruct_execution_context(raw, capability=secret)
    fake = {**context.review_context, field: value}
    with pytest.raises(ReviewError): registry.confirm(cid, fake, "confirm_post_office")


@pytest.mark.parametrize("first", ["confirm", "replacement"])
def test_both_replacement_confirmation_orderings_invalidate_old_confirmation(monkeypatch, first):
    registry, cid, _, _ = setup(monkeypatch)
    old_reference, _ = resolve(registry, cid)
    if first == "confirm": registry.confirm(cid, old_reference, "confirm_post_office")
    current, context = replacement(registry, cid)
    with pytest.raises(ReviewError): registry.confirm(cid, old_reference, "confirm_post_office")
    assert registry._records[cid].confirmed is None
    assert "post_office" not in context.facts
    assert registry.confirm(cid, current, "confirm_post_office").review_context == current


def test_ordinary_api_review_refresh_preserves_explicit_confirmation(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    registry, cid, secret, _ = setup(monkeypatch)
    resolve(registry, cid)
    import importlib
    api = importlib.import_module("api.app")
    client = TestClient(api.create_app(document_service=Mock()))
    headers = {"Authorization": "Bearer " + secret}
    base = "/api/review-contexts/" + cid
    review = client.get(base + "/review", headers=headers).json()
    response = client.post(base + "/action", headers=headers, json={"action": "confirm_post_office", "confirm_resolver_projection": True, "review_reference": review["review_reference"]})
    assert response.status_code == 200
    context = response.json()["confirmed_context"]
    confirmation = copy.deepcopy(registry._records[cid].confirmed)
    refreshed = client.get(base + "/review", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["review_reference"] == review["review_reference"]
    assert refreshed.json()["confirmed_context"] == context
    assert registry._records[cid].confirmed == confirmation
    assert reconstruct_execution_context(context, capability=secret).facts["pincode"].value == "641025"
