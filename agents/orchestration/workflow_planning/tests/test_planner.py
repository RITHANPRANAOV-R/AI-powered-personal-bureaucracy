from copy import deepcopy

from agents.knowledge_based.information_retrieval.schemas import (
    ConflictItem,
    Evidence,
    RetrievalResult,
    RetrievalStatus,
    Source,
    SourceType,
)
from agents.orchestration.intent_understanding.schemas import (
    ExtractedEntity,
    IntentClassificationResult,
    MissingInformation,
)
from agents.orchestration.monitoring.schemas import SessionState
from agents.orchestration.workflow_planning import (
    PlanStatus,
    PlanStep,
    StepStatus,
    StepType,
    WorkflowPlanningRequest,
    create_workflow_plan,
    validate_dependency_graph,
)


def _evidence(evidence_id: str, requirement_id: str, category: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        claim=f"Official {category} guidance",
        passage=f"Authoritative guidance for {category}.",
        source=Source(
            source_id=f"source-{evidence_id}",
            authority="UIDAI",
            domain="aadhaar",
            source_type=SourceType.OFFICIAL_FAQ,
        ),
        metadata={
            "associated_requirements": [requirement_id],
            "category": category,
        },
    )


def _request(
    *,
    intent_type: str = "update_request",
    update_type: str | None = "address",
    requirements: list[dict] | None = None,
    evidence: list[Evidence] | None = None,
    session_state: SessionState | None = None,
) -> WorkflowPlanningRequest:
    intent = IntentClassificationResult(
        session_id="session-1",
        intent_type=intent_type,
        update_type=update_type,
        summary="Aadhaar request",
        entities=[ExtractedEntity(entity_type="address", value="new address", normalized_value="new address")],
        confidence=0.95,
    )
    retrieval = RetrievalResult(
        result_id="result-1",
        request_id="session-1",
        service="Aadhaar",
        domain="aadhaar",
        retrieval_status=RetrievalStatus.SUCCESS if evidence else RetrievalStatus.NO_EVIDENCE_FOUND,
        requirements=requirements or [],
        evidence=evidence or [],
    )
    return WorkflowPlanningRequest(
        intent=intent,
        session_state=session_state,
        retrieved_evidence=retrieval,
    )


def test_address_update_creates_grounded_steps_and_approval():
    request = _request(
        requirements=[{"requirement_id": "address-proof", "category": "document", "description": "Prepare an accepted address proof."}],
        evidence=[_evidence("ev-address", "address-proof", "document")],
    )

    plan = create_workflow_plan(request)

    assert plan.task == "update"
    assert plan.target == "address"
    assert plan.plan_status == PlanStatus.READY
    requirement = next(step for step in plan.steps if step.step_id == "requirement-address-proof")
    assert requirement.evidence_ids == ["ev-address"]
    assert any(step.step_type == StepType.HUMAN_APPROVAL for step in plan.steps)
    assert plan.approval_points


def test_mobile_update_uses_current_intent_contract():
    request = _request(
        update_type="mobile_number",
        requirements=[{"requirement_id": "mobile-procedure", "category": "procedure", "description": "Follow the retrieved mobile update procedure."}],
        evidence=[_evidence("ev-mobile", "mobile-procedure", "procedure")],
    )

    plan = create_workflow_plan(request)

    assert plan.target == "mobile_number"
    assert "ev-mobile" in plan.evidence_ids


def test_missing_intent_information_is_preserved():
    request = _request(
        requirements=[{"requirement_id": "address-proof", "category": "document", "description": "Prepare an address proof."}],
        evidence=[_evidence("ev-address", "address-proof", "document")],
    )
    request.intent.missing_information.append(
        MissingInformation(field_name="new_address", reason="Please provide the new address.")
    )

    plan = create_workflow_plan(request)

    assert plan.plan_status == PlanStatus.NEEDS_USER_INPUT
    assert any(item.field_name == "new_address" for item in plan.missing_information)


def test_no_retrieved_requirements_creates_an_explicit_gap_without_fabrication():
    plan = create_workflow_plan(_request())

    assert plan.plan_status in {PlanStatus.PARTIAL, PlanStatus.NEEDS_USER_INPUT}
    assert not any(step.step_type == StepType.USER_ACTION for step in plan.steps)
    assert any("applicable Aadhaar requirements" in item.question for item in plan.missing_information)


def test_invalid_evidence_reference_is_not_silently_accepted():
    plan = create_workflow_plan(
        _request(
            requirements=[{"requirement_id": "name-proof", "category": "document", "description": "Prepare name proof.", "evidence_ids": ["does-not-exist"]}],
            evidence=[_evidence("ev-other", "other", "other")],
        )
    )

    assert not any(step.step_id == "requirement-name-proof" for step in plan.steps)
    assert any("unavailable evidence" in item.question for item in plan.missing_information)


def test_multiple_requirements_are_ordered_after_evidence_review():
    plan = create_workflow_plan(
        _request(
            requirements=[
                {"requirement_id": "r1", "category": "document", "description": "Prepare document one."},
                {"requirement_id": "r2", "category": "procedure", "description": "Follow procedure two."},
            ],
            evidence=[
                _evidence("ev-1", "r1", "document"),
                _evidence("ev-2", "r2", "procedure"),
            ],
        )
    )

    assert [step.sequence for step in plan.steps] == list(range(1, len(plan.steps) + 1))
    review = plan.steps[0]
    assert all(review.step_id in step.depends_on for step in plan.steps[1:3])


def test_dependency_cycle_is_reported():
    steps = [
        PlanStep(step_id="a", sequence=1, title="A", description="A", step_type=StepType.PREPARE_INFORMATION, depends_on=["b"]),
        PlanStep(step_id="b", sequence=2, title="B", description="B", step_type=StepType.PREPARE_INFORMATION, depends_on=["a"]),
    ]

    errors = validate_dependency_graph(steps)

    assert any("cycle" in error.lower() for error in errors)


def test_session_context_is_consumed_without_mutation():
    session = SessionState(
        session_id="session-1",
        intent_type="update_request",
        update_type="gender",
        summary="Existing gender update context",
        confidence=0.8,
    )
    before = deepcopy(session.model_dump())
    request = _request(update_type=None, session_state=session)

    plan = create_workflow_plan(request)

    assert plan.target == "gender"
    assert session.model_dump() == before


def test_conflicting_evidence_is_preserved_and_not_authorized():
    request = _request(
        requirements=[{"requirement_id": "r1", "category": "document", "description": "Prepare a document."}],
        evidence=[_evidence("ev-1", "r1", "document")],
    )
    request.retrieved_evidence.conflicts = [
        ConflictItem(conflict_id="conf-1", topic="document", description="Sources disagree.")
    ]

    plan = create_workflow_plan(request)

    assert plan.conflicts == ["document: Sources disagree."]
    assert not hasattr(plan, "execution_authorized")


def test_unknown_task_is_explicitly_blocked():
    plan = create_workflow_plan(_request(intent_type="complaint", update_type=None))

    assert plan.plan_status == PlanStatus.NEEDS_USER_INPUT
    assert plan.task == "unsupported"


def test_planner_has_no_monitoring_step_or_completion_claim():
    plan = create_workflow_plan(
        _request(
            requirements=[{"requirement_id": "r1", "category": "procedure", "description": "Follow the retrieved procedure."}],
            evidence=[_evidence("ev-1", "r1", "procedure")],
        )
    )

    assert all(step.step_type not in {StepType.EVIDENCE_GAP} for step in plan.steps)
    assert not any("track" in step.title.casefold() or "complete" in step.title.casefold() for step in plan.steps)
    assert all(step.status.value != "completed" for step in plan.steps)