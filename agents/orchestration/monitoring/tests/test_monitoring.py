from datetime import datetime, timedelta, timezone

from agents.orchestration.intent_understanding.schemas import ExtractedEntity, IntentRequest, IntentResult, MissingInformation
from agents.orchestration.intent_understanding.service import IntentUnderstandingService
from agents.orchestration.monitoring.schemas import ChangeDelta, MonitoringApplicationInput, MonitoringEvent, SessionState
from agents.orchestration.monitoring.service import MonitoringService


def build_state(**kwargs):
    default = {
        "session_id": "session-1",
        "intent_type": "update_request",
        "update_type": "address",
        "summary": "User wants to update Aadhaar address.",
        "entities": [ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)],
        "urgency": "normal",
        "missing_information": [],
        "confidence": 0.85,
        "last_updated": datetime.now(timezone.utc),
        "version": 1,
        "change_history": [
            ChangeDelta(
                field_name="status",
                previous_value=None,
                new_value="initial_state",
                change_type="initial_state",
                reason="Initial state created.",
            )
        ],
    }
    default.update(kwargs)
    return SessionState(**default)


def test_no_change():
    previous = build_state()
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.85,
    )

    result = MonitoringService().process(previous, new_intent)
    assert result.changes == []
    assert result.updated_state.intent_type == "update_request"


def test_address_update():
    previous = build_state()
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.90,
    )

    result = MonitoringService().process(previous, new_intent)
    assert len(result.changes) >= 1
    assert any(change.field_name == "confidence" for change in result.changes)


def test_mobile_number_update():
    previous = build_state(update_type="address")
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="mobile_number",
        summary="User wants to update mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.88,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.change_type == "intent_replaced" for change in result.changes)
    assert any(change.field_name == "update_type" for change in result.changes)


def test_new_entity_added():
    previous = build_state(entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)])
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address and email.",
        entities=[
            ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9),
            ExtractedEntity(entity_type="email", value="email", normalized_value="email", confidence=0.8),
        ],
        urgency="normal",
        missing_information=[],
        confidence=0.93,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.change_type == "field_added" for change in result.changes)


def test_missing_information_resolved():
    previous = build_state(missing_information=[MissingInformation(field_name="update_type", reason="Not specified", required=True, severity="medium")])
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.91,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.change_type == "missing_information_resolved" for change in result.changes)


def test_intent_replacement():
    previous = build_state(intent_type="status_inquiry", update_type=None)
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="mobile_number",
        summary="User now wants to update mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.9,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.field_name == "intent_type" for change in result.changes)


def test_contradictory_values():
    previous = build_state(summary="User wants to update Aadhaar address.")
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.9,
    )

    result = MonitoringService().process(previous, new_intent)
    assert any(change.change_type == "contradiction_detected" for change in result.changes)


def test_multiple_changes_in_one_message():
    previous = build_state(
        missing_information=[MissingInformation(field_name="update_type", reason="Not specified", required=True, severity="medium")],
        confidence=0.7,
    )
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[
            ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9),
            ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.8),
        ],
        urgency="normal",
        missing_information=[],
        confidence=0.95,
    )

    result = MonitoringService().process(previous, new_intent)
    assert len(result.changes) >= 3


def test_previous_state_not_mutated():
    previous = build_state()
    original_version = previous.version
    original_update_type = previous.update_type
    original_summary = previous.summary
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="mobile_number",
        summary="User wants to update mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="mobile_number", normalized_value="mobile_number", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.92,
    )

    MonitoringService().process(previous, new_intent)
    assert previous.version == original_version
    assert previous.update_type == original_update_type
    assert previous.summary == original_summary


def test_state_history_is_preserved():
    previous = build_state(change_history=[
        ChangeDelta(field_name="status", previous_value=None, new_value="initial_state", change_type="initial_state", reason="Initial state created."),
        ChangeDelta(field_name="status", previous_value="initial_state", new_value="first_update", change_type="field_updated", reason="History updated."),
    ])
    new_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="address", normalized_value="address", confidence=0.9)],
        urgency="normal",
        missing_information=[],
        confidence=0.9,
    )

    result = MonitoringService().process(previous, new_intent)
    assert len(result.updated_state.change_history) >= 2
    assert any(entry.change_type == "initial_state" for entry in result.updated_state.change_history)


def test_state_progression_for_address_then_mobile_number():
    state_1 = build_state(
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        missing_information=[MissingInformation(field_name="new_address", reason="Address update target is specified but not yet provided.", required=True, severity="medium")],
    )
    intent_2 = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="Coimbatore", normalized_value="coimbatore", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.92,
    )
    intent_3 = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="mobile_number",
        summary="User wants to update Aadhaar mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="9876543210", normalized_value="9876543210", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.94,
    )

    result_1 = MonitoringService().process(state_1, intent_2)
    assert result_1.updated_state.update_type == "address"
    assert any(change.field_name == "new_address" and change.change_type == "missing_information_resolved" for change in result_1.changes)

    result_2 = MonitoringService().process(result_1.updated_state, intent_3)
    assert result_2.updated_state.update_type == "mobile_number"
    assert any(change.field_name == "update_type" and change.change_type == "intent_replaced" for change in result_2.changes)
    assert any(change.change_type == "intent_replaced" for change in result_2.events)


def test_monitoring_application_input_contract():
    timestamp = datetime.now(timezone.utc)
    deadline = timestamp.replace(second=0, microsecond=0)
    payload = MonitoringApplicationInput(
        application_id="app-42",
        service_id="svc-42",
        service_type="aadhaar_update",
        current_status="pending_document",
        previous_status="new",
        timestamp=timestamp,
        required_action="Upload proof of address.",
        pending_action="Awaiting address proof review.",
        deadline=deadline,
        source="portal",
        event_type="status_changed",
        severity="medium",
        priority="normal",
        detected_at=timestamp,
        metadata={"request_id": "req-42", "retry": 0},
    )

    assert payload.application_id == "app-42"
    assert payload.service_id == "svc-42"
    assert payload.current_status == "pending_document"
    assert payload.previous_status == "new"
    assert payload.required_action == "Upload proof of address."
    assert payload.deadline == deadline
    assert payload.metadata["request_id"] == "req-42"


def test_monitoring_event_contract():
    detected_at = datetime.now(timezone.utc)
    event = MonitoringEvent(
        application_id="app-99",
        service_type="aadhaar_update",
        current_status="in_progress",
        previous_status="pending_document",
        timestamp=detected_at,
        required_action="Review submitted document.",
        pending_action="Awaiting verification.",
        deadline=detected_at,
        source="agent",
        event_type="document_received",
        severity="high",
        priority="high",
        detected_at=detected_at,
        metadata={"actor": "monitor"},
    )

    assert event.event_type == "document_received"
    assert event.severity == "high"
    assert event.priority == "high"
    assert event.metadata["actor"] == "monitor"


def test_detect_monitoring_events_for_status_and_action_changes():
    initial = MonitoringApplicationInput(
        application_id="app-100",
        service_id="svc-100",
        service_type="aadhaar_update",
        current_status="new",
        previous_status=None,
        timestamp=datetime.now(timezone.utc),
        required_action=None,
        pending_action="Waiting for applicant action.",
        source="portal",
        metadata={"stage": "init"},
    )
    document_required = MonitoringApplicationInput(
        application_id="app-100",
        service_id="svc-100",
        service_type="aadhaar_update",
        current_status="pending_document",
        previous_status="new",
        timestamp=datetime.now(timezone.utc),
        required_action="Upload proof of address.",
        pending_action="Awaiting document review.",
        source="portal",
        metadata={"stage": "document"},
    )
    blocked = MonitoringApplicationInput(
        application_id="app-100",
        service_id="svc-100",
        service_type="aadhaar_update",
        current_status="workflow_failed",
        previous_status="pending_document",
        timestamp=datetime.now(timezone.utc),
        required_action="Correct the Aadhaar name mismatch.",
        pending_action="Verification blocked pending correction.",
        source="portal",
        metadata={"stage": "correction"},
    )
    completed = MonitoringApplicationInput(
        application_id="app-100",
        service_id="svc-100",
        service_type="aadhaar_update",
        current_status="completed",
        previous_status="workflow_failed",
        timestamp=datetime.now(timezone.utc),
        required_action=None,
        pending_action="Application completed successfully.",
        source="portal",
        metadata={"stage": "completed"},
    )

    event_sequence = []
    for previous, current in [(initial, document_required), (document_required, blocked), (blocked, completed)]:
        event_sequence.extend(MonitoringService().detect_events(previous, current))

    event_types = {event.event_type for event in event_sequence}
    assert {"status_changed", "required_action_detected", "document_required", "correction_required", "workflow_blocked", "completed"}.issubset(event_types)


def test_detect_monitoring_events_unchanged_state():
    payload = MonitoringApplicationInput(
        application_id="app-101",
        service_id="svc-101",
        service_type="aadhaar_update",
        current_status="pending_document",
        previous_status="new",
        timestamp=datetime.now(timezone.utc),
        required_action="Upload proof of address.",
        pending_action="Awaiting document review.",
        source="portal",
        metadata={"stage": "document"},
    )

    assert MonitoringService().detect_events(payload, payload) == []


def test_monitoring_end_to_end_action_required_event_without_notification():
    now = datetime.now(timezone.utc)
    processing = MonitoringApplicationInput(
        application_id="app-300",
        service_id="svc-300",
        service_type="aadhaar_update",
        current_status="PROCESSING",
        previous_status="SUBMITTED",
        timestamp=now - timedelta(hours=2),
        required_action=None,
        pending_action="Application is being processed.",
        source="portal",
        metadata={"stage": "processing"},
    )
    action_required = MonitoringApplicationInput(
        application_id="app-300",
        service_id="svc-300",
        service_type="aadhaar_update",
        current_status="ACTION_REQUIRED",
        previous_status="PROCESSING",
        timestamp=now,
        required_action="Upload proof of address.",
        pending_action="Awaiting address proof.",
        source="portal",
        metadata={"stage": "action_required"},
    )

    events = MonitoringService().detect_events(processing, action_required)
    assert events

    matching_event = next(
        event for event in events
        if event.event_type in {"status_changed", "required_action_detected"}
    )
    assert matching_event.previous_status == "PROCESSING"
    assert matching_event.current_status == "ACTION_REQUIRED"
    assert matching_event.required_action == "Upload proof of address."
    assert matching_event.detected_at == action_required.detected_at
    assert matching_event.source == "portal"
    assert all("notification" not in str(event.metadata).lower() for event in events)
    assert all("notification" not in str(event.event_type).lower() for event in events)


def test_detect_missing_status_data_yields_no_event():
    now = datetime.now(timezone.utc)
    previous = MonitoringApplicationInput(
        application_id="app-205",
        service_id="svc-205",
        service_type="aadhaar_update",
        current_status="pending_document",
        previous_status="new",
        timestamp=now - timedelta(days=1),
        required_action="Upload proof of address.",
        pending_action="Awaiting document review.",
        source="portal",
        metadata={"stage": "document"},
    )
    current = MonitoringApplicationInput(
        application_id="app-205",
        service_id="svc-205",
        service_type="aadhaar_update",
        current_status="unknown",
        previous_status="pending_document",
        timestamp=now,
        required_action="Upload proof of address.",
        pending_action="Awaiting document review.",
        source="portal",
        metadata={"status": "unavailable"},
    )

    assert MonitoringService().detect_events(previous, current) == []


def test_detect_unavailable_status_data_yields_no_event():
    now = datetime.now(timezone.utc)
    payload = MonitoringApplicationInput(
        application_id="app-206",
        service_id="svc-206",
        service_type="aadhaar_update",
        current_status="unavailable",
        previous_status="unknown",
        timestamp=now,
        required_action=None,
        pending_action=None,
        source="portal",
        metadata={"status": "unavailable"},
    )

    assert MonitoringService().detect_events(None, payload) == []


def test_detect_deadline_approaching_event():
    now = datetime.now(timezone.utc)
    previous = MonitoringApplicationInput(
        application_id="app-200",
        service_id="svc-200",
        service_type="aadhaar_update",
        current_status="pending_document",
        previous_status="new",
        timestamp=now - timedelta(days=1),
        required_action="Upload proof of address.",
        pending_action="Awaiting document review.",
        source="portal",
        metadata={"stage": "document"},
    )
    current = MonitoringApplicationInput(
        application_id="app-200",
        service_id="svc-200",
        service_type="aadhaar_update",
        current_status="pending_document",
        previous_status="new",
        timestamp=now,
        required_action="Upload proof of address.",
        pending_action="Awaiting document review.",
        deadline=now + timedelta(days=2),
        source="portal",
        metadata={"stage": "document"},
    )

    events = MonitoringService().detect_events(previous, current)
    assert any(event.event_type == "DEADLINE_APPROACHING" for event in events)


def test_detect_deadline_missed_event():
    now = datetime.now(timezone.utc)
    previous = MonitoringApplicationInput(
        application_id="app-201",
        service_id="svc-201",
        service_type="aadhaar_update",
        current_status="pending_document",
        previous_status="new",
        timestamp=now - timedelta(days=3),
        required_action="Upload proof of address.",
        pending_action="Awaiting document review.",
        deadline=now - timedelta(days=1),
        source="portal",
        metadata={"stage": "document"},
    )
    current = MonitoringApplicationInput(
        application_id="app-201",
        service_id="svc-201",
        service_type="aadhaar_update",
        current_status="pending_document",
        previous_status="pending_document",
        timestamp=now,
        required_action="Upload proof of address.",
        pending_action="Awaiting document review.",
        deadline=now - timedelta(days=1),
        source="portal",
        metadata={"stage": "document"},
    )

    events = MonitoringService().detect_events(previous, current)
    assert any(event.event_type == "DEADLINE_MISSED" for event in events)


def test_detect_appointment_approaching_event():
    now = datetime.now(timezone.utc)
    previous = MonitoringApplicationInput(
        application_id="app-202",
        service_id="svc-202",
        service_type="aadhaar_update",
        current_status="appointment_scheduled",
        previous_status="in_progress",
        timestamp=now - timedelta(days=1),
        required_action="Attend the Aadhaar appointment.",
        pending_action="Appointment scheduled for verification.",
        source="portal",
        metadata={"stage": "appointment"},
    )
    current = MonitoringApplicationInput(
        application_id="app-202",
        service_id="svc-202",
        service_type="aadhaar_update",
        current_status="appointment_scheduled",
        previous_status="in_progress",
        timestamp=now,
        required_action="Attend the Aadhaar appointment.",
        pending_action="Appointment scheduled for verification.",
        deadline=now + timedelta(hours=6),
        source="portal",
        metadata={"stage": "appointment"},
    )

    events = MonitoringService().detect_events(previous, current)
    assert any(event.event_type == "APPOINTMENT_APPROACHING" for event in events)


def test_detect_processing_delay_event():
    now = datetime.now(timezone.utc)
    previous = MonitoringApplicationInput(
        application_id="app-203",
        service_id="svc-203",
        service_type="aadhaar_update",
        current_status="processing",
        previous_status="processing",
        timestamp=now - timedelta(days=3),
        required_action=None,
        pending_action="Application is being processed.",
        source="portal",
        metadata={"stage": "processing"},
    )
    current = MonitoringApplicationInput(
        application_id="app-203",
        service_id="svc-203",
        service_type="aadhaar_update",
        current_status="processing",
        previous_status="processing",
        timestamp=now,
        required_action=None,
        pending_action="Application is being processed.",
        source="portal",
        metadata={"stage": "processing"},
    )

    events = MonitoringService().detect_events(previous, current)
    assert any(event.event_type == "PROCESSING_DELAY" for event in events)


def test_detect_deadline_events_unchanged_state_no_emission():
    now = datetime.now(timezone.utc)
    payload = MonitoringApplicationInput(
        application_id="app-204",
        service_id="svc-204",
        service_type="aadhaar_update",
        current_status="processing",
        previous_status="processing",
        timestamp=now,
        required_action=None,
        pending_action="Application is being processed.",
        deadline=now + timedelta(days=1),
        source="portal",
        metadata={"stage": "processing"},
    )

    assert MonitoringService().detect_events(payload, payload) == []


def test_end_to_end_aadhaar_update_and_status_flow():
    service = IntentUnderstandingService()
    session_id = "session-e2e-1"
    previous_state = None

    message_1 = IntentRequest(session_id=session_id, user_message="I want to update my Aadhaar address.")
    intent_1 = service.process(message_1)
    assert intent_1.intent_type == "update_request"
    assert intent_1.update_type == "address"
    assert any(item.field_name == "new_address" for item in intent_1.missing_information)

    monitoring_1 = MonitoringService().process(previous_state, intent_1)
    previous_state = monitoring_1.updated_state
    assert previous_state.update_type == "address"
    assert any(item.field_name == "new_address" for item in previous_state.missing_information)

    message_2 = IntentRequest(
        session_id=session_id,
        user_message="My new address is Coimbatore.",
        current_session_state=previous_state.model_dump(),
    )
    intent_2 = service.process(message_2)
    assert any(entity.entity_type == "address" and entity.value.lower() == "coimbatore" for entity in intent_2.entities)
    monitoring_2 = MonitoringService().process(previous_state, intent_2)
    previous_state = monitoring_2.updated_state
    assert previous_state.update_type == "address"
    assert any(change.change_type == "missing_information_resolved" for change in monitoring_2.changes)
    assert not any(item.field_name == "new_address" for item in previous_state.missing_information)

    message_3 = IntentRequest(
        session_id=session_id,
        user_message="Actually, I want to change my mobile number.",
        current_session_state=previous_state.model_dump(),
    )
    intent_3 = service.process(message_3)
    assert intent_3.intent_type == "update_request"
    assert intent_3.update_type == "mobile_number"
    monitoring_3 = MonitoringService().process(previous_state, intent_3)
    previous_state = monitoring_3.updated_state
    assert previous_state.update_type == "mobile_number"
    assert any(change.field_name == "update_type" and change.change_type == "intent_replaced" for change in monitoring_3.changes)

    status_message_1 = IntentRequest(session_id=session_id, user_message="I want to check my Aadhaar update status.")
    status_intent_1 = service.process(status_message_1)
    assert status_intent_1.intent_type == "status_inquiry"
    assert status_intent_1.update_type is None

    status_message_2 = IntentRequest(
        session_id=session_id,
        user_message="I updated my address last week, what is the status?",
        current_session_state=previous_state.model_dump(),
    )
    status_intent_2 = service.process(status_message_2)
    assert status_intent_2.intent_type == "status_inquiry"
    assert status_intent_2.update_type is None
    assert status_intent_2.summary.lower().startswith("user wants to check")


def test_public_monitoring_contract_for_downstream_state_consumers():
    initial_state = build_state(
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        missing_information=[MissingInformation(field_name="new_address", reason="Address update target is specified but not yet provided.", required=True, severity="medium")],
    )
    resolved_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="address",
        summary="User wants to update Aadhaar address.",
        entities=[ExtractedEntity(entity_type="address", value="Coimbatore", normalized_value="coimbatore", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.92,
    )
    transition_intent = IntentResult(
        session_id="session-1",
        intent_type="update_request",
        update_type="mobile_number",
        summary="User wants to update Aadhaar mobile number.",
        entities=[ExtractedEntity(entity_type="mobile_number", value="9876543210", normalized_value="9876543210", confidence=0.95)],
        urgency="normal",
        missing_information=[],
        confidence=0.94,
    )

    resolved = MonitoringService().process(initial_state, resolved_intent)
    assert resolved.updated_state.intent_type == "update_request"
    assert resolved.updated_state.update_type == "address"
    assert any(change.change_type == "missing_information_resolved" for change in resolved.changes)

    transitioned = MonitoringService().process(resolved.updated_state, transition_intent)
    assert transitioned.updated_state.update_type == "mobile_number"
    assert any(change.field_name == "update_type" and change.change_type == "intent_replaced" for change in transitioned.changes)
    assert all(change.field_name != "new_address" for change in transitioned.changes if change.change_type == "field_added")


def test_end_to_end_intent_understanding_and_monitoring_flow():
    from agents.orchestration.intent_understanding.service import IntentUnderstandingService

    message_1 = "I want to update my Aadhaar address."
    result_1 = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session",
        user_message=message_1,
    ))

    assert result_1.intent_type == "update_request"
    assert result_1.update_type == "address"
    assert any(item.field_name == "new_address" for item in result_1.missing_information)

    state_1 = SessionState(
        session_id=result_1.session_id,
        intent_type=result_1.intent_type,
        update_type=result_1.update_type,
        summary=result_1.summary,
        entities=result_1.entities,
        urgency=result_1.urgency,
        missing_information=result_1.missing_information,
        confidence=result_1.confidence,
        last_updated=datetime.now(timezone.utc),
        version=1,
        change_history=[
            ChangeDelta(
                field_name="status",
                previous_value=None,
                new_value="initial_state",
                change_type="initial_state",
                reason="Initial state created.",
            )
        ],
    )

    message_2 = "My new address is Coimbatore."
    result_2 = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session",
        user_message=message_2,
    ))

    assert any(entity.entity_type == "address" and entity.value.lower() == "coimbatore" for entity in result_2.entities)
    monitored_2 = MonitoringService().process(state_1, result_2)
    assert monitored_2.updated_state.update_type == "address"
    assert any(change.change_type == "missing_information_resolved" for change in monitored_2.changes)
    assert not any(item.field_name == "new_address" for item in monitored_2.updated_state.missing_information)

    message_3 = "Actually, I want to change my mobile number."
    result_3 = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session",
        user_message=message_3,
    ))

    assert result_3.intent_type == "update_request"
    assert result_3.update_type == "mobile_number"
    monitored_3 = MonitoringService().process(monitored_2.updated_state, result_3)
    assert monitored_3.updated_state.update_type == "mobile_number"
    assert any(change.field_name == "update_type" and change.change_type == "intent_replaced" for change in monitored_3.changes)

    status_check = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session-status",
        user_message="I want to check my Aadhaar update status.",
    ))
    assert status_check.intent_type == "status_inquiry"
    assert status_check.update_type is None

    status_follow_up = IntentUnderstandingService().process(IntentRequest(
        session_id="integration-session-status-2",
        user_message="I updated my address last week, what is the status?",
    ))
    assert status_follow_up.intent_type == "status_inquiry"
    assert status_follow_up.update_type is None
