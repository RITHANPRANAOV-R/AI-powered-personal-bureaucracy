"""B.3.5 security/lifecycle tests; synthetic evidence and mocked browser only."""
import asyncio
from unittest.mock import AsyncMock, Mock, patch
import pytest
from fastapi.testclient import TestClient
from agents.utility_based.execution_assistance.tests.test_address_projection import resolved_context, PIN
from agents.utility_based.execution_assistance.review_context import ReviewRegistry, ReviewError
from agents.utility_based.execution_assistance.context_validator import reconstruct_execution_context, apply_context_corrections
from agents.utility_based.execution_assistance.interactive_session import InteractivePortalManager, ActiveBrowserSession
from agents.utility_based.execution_assistance.schema import ActionExecutionResult, ExecutionOutcome
from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver
from agents.knowledge_based.information_retrieval.tests.test_address_resolver import lookup, postal_record


def clean():
    _, extraction, data, context = resolved_context()
    context.facts.pop("address_resolution")
    return context, extraction


def result_for(context, office="Alpha Office", multiple=False):
    pin = context.facts["pincode"].value
    records = [postal_record(office, pincode=pin)]
    if multiple:
        records.append(postal_record("Beta Office", pincode=pin))
    return PostalAddressResolver().resolve(pin, {k: f.value for k, f in context.facts.items()}, lookup(records, queried_pin=pin))


def setup(monkeypatch, **options):
    from agents.utility_based.execution_assistance import review_context
    registry = ReviewRegistry(**options)
    monkeypatch.setattr(review_context, "review_registry", registry)
    context, extraction = clean()
    context_id, secret, context = registry.create(context)
    return registry, context_id, secret, context


def resolve(registry, context_id, multiple=False):
    generation, context = registry.begin_lookup(context_id)
    registry.finish_lookup(context_id, generation, result_for(context, multiple=multiple))
    return registry.publish(context_id)


def confirmed(registry, context_id):
    reference, context = resolve(registry, context_id)
    return registry.confirm(context_id, reference, "confirm_post_office")


@pytest.mark.parametrize("secret", [None, "", "wrong", "public-id"])
def test_capability_required(monkeypatch, secret):
    registry, context_id, _, context = setup(monkeypatch)
    with pytest.raises(ReviewError): registry.authenticate(context_id, secret)


def test_secret_verifier_only_and_scope(monkeypatch):
    registry, context_id, secret, context = setup(monkeypatch)
    registry.authenticate(context_id, secret, context.session_id)
    assert len(secret) >= 43
    assert secret not in repr(registry._records)
    assert secret not in context.model_dump_json()
    other_id, other_secret, other = registry.create(clean()[0])
    with pytest.raises(ReviewError): registry.authenticate(other_id, secret)
    with pytest.raises(ReviewError): registry.authenticate(context_id, secret, other.session_id)
    with pytest.raises(ReviewError): registry.authenticate("guessed", secret)


def test_review_is_not_confirmation_and_exact_pin_preserved(monkeypatch):
    registry, context_id, secret, _ = setup(monkeypatch)
    reference, reviewed = resolve(registry, context_id)
    assert "post_office" not in reviewed.facts
    with pytest.raises(ReviewError): registry.reserve_launch(reviewed)
    projected = registry.confirm(context_id, reference, "confirm_post_office")
    assert projected.facts["post_office"].value == "Alpha Office"
    assert projected.facts["pincode"].value == PIN == "641025"
    assert all(key not in projected.facts for key in ["state", "district", "vtc", "locality"])
    for action in ["review", "confirmed", "next", "Approve & Submit"]:
        with pytest.raises(ReviewError): registry.confirm(context_id, reference, action)


@pytest.mark.parametrize("field,value", [("id", "another"), ("generation", 99), ("input_revision", 99), ("result_binding", "fabricated")])
def test_exact_review_reference(monkeypatch, field, value):
    registry, context_id, _, _ = setup(monkeypatch)
    reference, _ = resolve(registry, context_id)
    with pytest.raises(ReviewError): registry.confirm(context_id, {**reference, field: value}, "confirm_post_office")


def test_distinct_generations_late_responses_and_failed_lookup(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    first, inputs = registry.begin_lookup(context_id)
    second, current = registry.begin_lookup(context_id)
    assert first != second
    with pytest.raises(ReviewError): registry.finish_lookup(context_id, first, result_for(inputs))
    registry.finish_lookup(context_id, second, result_for(current))
    old_ref, _ = registry.publish(context_id)
    registry.confirm(context_id, old_ref, "confirm_post_office")
    third, _ = registry.begin_lookup(context_id)
    registry.finish_lookup(context_id, third)
    assert registry.snapshot(context_id).address_resolution is None
    with pytest.raises(ReviewError): registry.confirm(context_id, old_ref, "confirm_post_office")
    with pytest.raises(ReviewError): registry.publish(context_id)


@pytest.mark.parametrize("key,value", [("pincode", "560001"), ("new_address", "Corrected address"),
    ("vtc", "Citizen town"), ("city", "Citizen city"), ("post_office", "Citizen PO"),
    ("locality", "Citizen locality"), ("area", "Citizen area")])
def test_shared_correction_invalidation(monkeypatch, key, value):
    registry, context_id, _, _ = setup(monkeypatch)
    projected = confirmed(registry, context_id)
    old_reference = dict(projected.review_context)
    with patch.object(PostalAddressResolver, "resolve") as resolver:
        corrected = apply_context_corrections(projected, {key: value})
        resolver.assert_not_called()
    assert corrected.facts[key].value == value
    assert corrected.address_resolution is None
    assert not any(f.resolution_projection for f in corrected.facts.values())
    assert corrected.review_context["input_revision"] > old_reference["input_revision"]
    with pytest.raises(ReviewError): registry.confirm(context_id, old_reference, "confirm_post_office")


def test_non_address_edit_preserves_projection(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    context = confirmed(registry, context_id)
    corrected = apply_context_corrections(context, {"name": "Corrected citizen"})
    assert corrected.facts["post_office"] == context.facts["post_office"]
    assert corrected.review_context == context.review_context
    registry.validate(corrected)


def test_expiry_revocation_restart_and_capacity(monkeypatch):
    now = [0]
    registry, context_id, secret, context = setup(monkeypatch, capacity=1, lifetime=10, clock=lambda: now[0])
    with pytest.raises(ReviewError): registry.create(clean()[0])
    now[0] = 10
    with pytest.raises(ReviewError): registry.authenticate(context_id, secret)
    new_id, new_secret, _ = registry.create(clean()[0])
    registry.revoke(new_id)
    with pytest.raises(ReviewError): registry.authenticate(new_id, new_secret)
    with pytest.raises(ReviewError): ReviewRegistry().authenticate(context_id, secret)


def test_reconstruction_rejects_fabrication_and_stripped_reference(monkeypatch):
    registry, context_id, secret, _ = setup(monkeypatch)
    context = confirmed(registry, context_id)
    raw = context.model_dump(mode="json")
    assert reconstruct_execution_context(raw, capability=secret) == context
    for change in ["strip", "pin", "office", "revision"]:
        import copy
        fake = copy.deepcopy(raw)
        if change == "strip": fake.pop("review_context")
        elif change == "pin": fake["facts"]["pincode"]["value"] = "560001"
        elif change == "office": fake["facts"]["post_office"]["value"] = "Fake office"
        else: fake["review_context"]["input_revision"] = 99
        with pytest.raises(ValueError): reconstruct_execution_context(fake, capability=secret)


def test_launch_replay_execution_reservation_and_uncertain_outcome(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    context = confirmed(registry, context_id)
    registry.reserve_launch(context)
    with pytest.raises(ReviewError): registry.reserve_launch(context)
    with pytest.raises(ReviewError): apply_context_corrections(context, {"pincode": "560001"})
    registry.finish_launch(context_id, True)
    registry.begin_execution(context)
    with pytest.raises(ReviewError): registry.begin_execution(context)
    with pytest.raises(ReviewError): apply_context_corrections(context, {"name": "Concurrent edit"})
    registry.end_execution(context_id)
    with pytest.raises(ReviewError): registry.reserve_launch(context)
    other_id, _, other = registry.create(clean()[0])
    registry.reserve_launch(other); registry.finish_launch(other_id, False)
    with pytest.raises(ReviewError): registry.reserve_launch(other)


def test_direct_manager_correction_and_dispatch_check(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    context = confirmed(registry, context_id)
    manager = InteractivePortalManager()
    manager._launch_and_navigate_login = AsyncMock()
    asyncio.run(manager.start_session(context))
    manager._execute_stage_action_on_portal = AsyncMock(return_value=ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Synthetic checkpoint"))
    result = asyncio.run(manager.submit_step(context.session_id, True, user_inputs={"pincode": "560001"}))
    assert result["is_completed"] is False
    session = manager._sessions[context.session_id]
    assert session.context.facts["pincode"].value == "560001"
    assert session.context.address_resolution is None
    assert "post_office" not in session.context.facts
    manager._execute_stage_action_on_portal.reset_mock()
    registry.revoke(context_id)
    asyncio.run(manager.submit_step(context.session_id, True))
    manager._execute_stage_action_on_portal.assert_not_awaited()


def test_manager_independently_rejects_fabricated_handoff(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    context = confirmed(registry, context_id)
    context.review_context["generation"] += 1
    manager = InteractivePortalManager()
    manager._launch_and_navigate_login = AsyncMock()
    with pytest.raises(ReviewError): asyncio.run(manager.start_session(context))
    manager._launch_and_navigate_login.assert_not_awaited()


def test_ambiguous_result_cannot_confirm(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    reference, context = resolve(registry, context_id, multiple=True)
    assert context.address_resolution.candidates
    with pytest.raises(ReviewError): registry.confirm(context_id, reference, "confirm_post_office")


def test_api_scoped_sequence_and_fabrication(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    registry, _, _, _ = setup(monkeypatch)
    import api.app as ignored
    import importlib
    api = importlib.import_module("api.app")
    context, extraction = clean()
    service = Mock()
    # Use the real document confirmation, synthetic resolver output only.
    service, extraction, _, _ = resolved_context()
    service.address_resolver = Mock(spec=PostalAddressResolver)
    service.address_resolver.resolve.side_effect = lambda pin, inputs: PostalAddressResolver().resolve(pin, inputs, lookup([postal_record(pincode=pin)], queried_pin=pin))
    client = TestClient(api.create_app(document_service=service))
    created = client.post("/api/documents/aadhaar/confirm", json={"confirmed": True, "extraction": extraction.model_dump(mode="json")})
    assert created.status_code == 200
    body = created.json(); secret = body.pop("review_capability")
    context_id = body["confirmed_context"]["review_context"]["id"]
    headers = {"Authorization": "Bearer " + secret, "X-Review-Context": context_id}
    base = "/api/review-contexts/" + context_id
    assert client.post(base + "/resolve").status_code == 403
    assert client.post(base + "/resolve", headers=headers).status_code == 200
    response = client.get(base + "/review", headers=headers)
    assert response.status_code == 200
    assert secret not in response.text
    reviewed = response.json()
    rejected = client.post(base + "/action", headers=headers, json={"action": "confirm_post_office", "confirm_resolver_projection": True, "address_resolution": reviewed["confirmed_data"]["address_resolution"]})
    assert rejected.status_code == 409
    projected = client.post(base + "/action", headers=headers, json={"action": "confirm_post_office", "confirm_resolver_projection": True, "review_reference": reviewed["review_reference"]})
    assert projected.status_code == 200, projected.text
    assert projected.json()["confirmed_context"]["facts"]["pincode"]["value"] == PIN
    assert client.post(base + "/action", headers=headers, json={"action": "correct", "corrections": {"pincode": "560001"}}).status_code == 200
    assert client.post(base + "/action", headers=headers, json={"action": "confirm_post_office", "confirm_resolver_projection": True, "review_reference": reviewed["review_reference"]}).status_code == 409
    assert client.post(base + "/action", headers=headers, json={"action": "cancel"}).status_code == 200
    assert client.get(base + "/review", headers=headers).status_code == 403


def test_execution_concurrency_without_locks_across_browser_await(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    context = confirmed(registry, context_id)
    manager = InteractivePortalManager()
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        async def launch(session):
            assert not manager._lock.locked()
            assert not registry._lock._is_owned()
        manager._launch_and_navigate_login = launch
        await manager.start_session(context)
        async def action(*args):
            assert not manager._lock.locked()
            assert not registry._lock._is_owned()
            started.set()
            await release.wait()
            return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Synthetic wait")
        manager._execute_stage_action_on_portal = AsyncMock(side_effect=action)
        first = asyncio.create_task(manager.submit_step(context.session_id, True))
        await started.wait()
        concurrent = await manager.submit_step(context.session_id, True)
        assert concurrent["execution_result"]["status"] == "BLOCKED"
        with pytest.raises(ReviewError): registry.begin_lookup(context_id)
        with pytest.raises(ReviewError): registry.revoke(context_id)
        release.set()
        await first
        manager._execute_stage_action_on_portal.assert_awaited_once()
    asyncio.run(scenario())


def test_active_session_can_resolve_after_correction_without_relaunch(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    context = confirmed(registry, context_id)
    registry.reserve_launch(context); registry.finish_launch(context_id, True)
    corrected = apply_context_corrections(context, {"pincode": "560001"})
    reservation, inputs = registry.begin_lookup(context_id)
    with pytest.raises(ReviewError): registry.begin_execution(registry.snapshot(context_id))
    registry.finish_lookup(context_id, reservation, result_for(inputs))
    reference, _ = registry.publish(context_id)
    current = registry.confirm(context_id, reference, "confirm_post_office")
    registry.begin_execution(current); registry.end_execution(context_id)
    with pytest.raises(ReviewError): registry.reserve_launch(current)
    assert current.session_id == context.session_id
    assert current.facts["pincode"].value == "560001"


def test_prior_publication_and_typed_reference_cannot_be_replayed(monkeypatch):
    registry, context_id, _, _ = setup(monkeypatch)
    reference, _ = resolve(registry, context_id)
    repeated, _ = registry.publish(context_id)
    assert repeated == reference
    newer, _ = resolve(registry, context_id)
    assert newer != reference
    with pytest.raises(ReviewError): registry.confirm(context_id, reference, "confirm_post_office")
    wrong_type = {**newer, "input_revision": False}
    with pytest.raises(ReviewError): registry.confirm(context_id, wrong_type, "confirm_post_office")


def test_bad_correction_and_size_limits_do_not_mutate_state(monkeypatch):
    registry, context_id, _, context = setup(monkeypatch)
    before = context.model_dump_json()
    for edits in [["not-mapping"], {"review_capability": "secret"}, {"new_address": "x" * (1024 * 1024 + 1)}]:
        with pytest.raises(ValueError): apply_context_corrections(context, edits)
        assert registry.snapshot(context_id).model_dump_json() == before


@pytest.mark.parametrize("failure", ["serialization", "structure", "copy"])
def test_lookup_completion_failure_clears_only_current_generation(monkeypatch, failure):
    registry, cid, _, _ = setup(monkeypatch)
    confirmed(registry, cid)
    reservation, context = registry.begin_lookup(cid)
    result = result_for(context)
    if failure == "serialization":
        result = Mock()
        result.model_dump_json.side_effect = RuntimeError("Synthetic serialization failure")
    elif failure == "structure":
        from agents.utility_based.execution_assistance import review_context
        monkeypatch.setattr(review_context.ConfirmedExecutionContext, "model_validate", Mock(side_effect=ValueError("Synthetic structure failure")))
    else:
        result = Mock(wraps=result)
        result.model_copy.side_effect = RuntimeError("Synthetic copy failure")
    with pytest.raises((ValueError, RuntimeError)):
        registry.finish_lookup(cid, reservation, result)
    record = registry._records[cid]
    assert record.lookup_status == "failed"
    assert record.result is record.published is record.confirmed is record.projected_fact is None
    newer, _ = registry.begin_lookup(cid)
    assert newer != reservation
    registry.fail_lookup(cid, reservation)
    assert record.lookup_status == "pending"


@pytest.mark.parametrize("change", ["replacement", "correction", "cancel"])
def test_old_lookup_cleanup_never_invalidates_new_authority(monkeypatch, change):
    registry, cid, _, _ = setup(monkeypatch)
    old, _ = registry.begin_lookup(cid)
    if change == "correction":
        corrected = apply_context_corrections(registry.snapshot(cid), {"pincode": "560001"})
        assert corrected.facts["pincode"].value == "560001"
    elif change == "cancel":
        registry.revoke(cid)
        registry.fail_lookup(cid, old)
        assert registry._records[cid].revoked
        with pytest.raises(ReviewError): registry.snapshot(cid)
        return
    new, context = registry.begin_lookup(cid)
    registry.fail_lookup(cid, old)
    assert registry._records[cid].lookup_status == "pending"
    with pytest.raises(ReviewError): registry.finish_lookup(cid, old, result_for(context))
    registry.finish_lookup(cid, new, result_for(context))
    reference, _ = registry.publish(cid)
    projected = registry.confirm(cid, reference, "confirm_post_office")
    registry.fail_lookup(cid, old)
    assert registry.snapshot(cid) == projected
    assert projected.facts["pincode"].value == ("560001" if change == "correction" else "641025")


def test_capability_auth_error_code_is_distinct_from_origin_rejection(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    registry, cid, _, _ = setup(monkeypatch)
    import importlib
    api = importlib.import_module("api.app")
    client = TestClient(api.create_app(document_service=Mock()))
    path = "/api/review-contexts/" + cid + "/review"
    authentication = client.get(path)
    assert authentication.status_code == 403
    assert authentication.json()["detail"]["code"] == "REVIEW_CAPABILITY_AUTH_FAILED"
    origin = client.get(path, headers={"Origin": "https://unrelated.example"})
    assert origin.status_code == 403
    assert origin.json()["detail"] == "Frontend origin is not permitted."


@pytest.mark.parametrize("failure", ["synchronization", "resolver", "completion"])
def test_resolve_endpoint_cleanup_on_cancel_or_validation_failure(monkeypatch, failure):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    registry, cid, secret, _ = setup(monkeypatch)
    import importlib
    from fastapi import HTTPException
    from starlette.requests import Request
    from agents.utility_based.execution_assistance.interactive_session import interactive_manager
    api = importlib.import_module("api.app")
    app = api.create_app(document_service=Mock())
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/api/review-contexts/{context_id}/resolve")
    request = Request({"type": "http", "headers": [(b"authorization", ("Bearer " + secret).encode())]})
    class CancelledSynchronization:
        async def __aenter__(self):
            raise asyncio.CancelledError()
        async def __aexit__(self, *args):
            return False
    if failure == "synchronization":
        monkeypatch.setattr(interactive_manager, "_lock", CancelledSynchronization())
    elif failure == "resolver":
        import starlette.concurrency
        monkeypatch.setattr(starlette.concurrency, "run_in_threadpool", AsyncMock(side_effect=asyncio.CancelledError()))
    else:
        import starlette.concurrency
        malformed = Mock()
        malformed.model_dump_json.side_effect = ValueError("Synthetic invalid output")
        monkeypatch.setattr(starlette.concurrency, "run_in_threadpool", AsyncMock(return_value=malformed))
    with pytest.raises(HTTPException if failure == "completion" else asyncio.CancelledError):
        asyncio.run(endpoint(cid, request))
    record = registry._records[cid]
    assert record.lookup_status == "failed"
    assert record.result is record.confirmed is record.published is record.projected_fact is None
    replacement, _ = registry.begin_lookup(cid)
    assert replacement[1] > 1
