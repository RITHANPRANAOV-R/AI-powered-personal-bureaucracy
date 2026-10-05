from agents.orchestration.pipeline import OrchestrationStatus

from .run_demo import run_scenario


def test_happy_path_completes():
    result, runtime = run_scenario("happy_path")

    assert result.status == OrchestrationStatus.EXECUTION_COMPLETED
    assert result.integration_result.compliance_decision.allowed is True
    assert result.integration_result.execution_result.status.value == "completed"
    assert runtime.execution.calls


def test_missing_information_stops_before_retrieval_and_execution():
    result, runtime = run_scenario("missing_information")

    assert result.status == OrchestrationStatus.NEEDS_CLARIFICATION
    assert runtime.retrieval.calls == 0
    assert runtime.execution.calls == []


def test_compliance_warning_blocks_execution():
    result, runtime = run_scenario("compliance_warning")

    assert result.status == OrchestrationStatus.COMPLIANCE_BLOCKED
    assert result.integration_result.compliance_decision.allowed is False
    assert runtime.execution.calls == []


def test_compliance_blocked_blocks_execution():
    result, runtime = run_scenario("compliance_blocked")

    assert result.status == OrchestrationStatus.COMPLIANCE_BLOCKED
    assert "blocked" in result.blocking_reason.lower()
    assert runtime.execution.calls == []


def test_human_intervention_preserves_checkpoint():
    result, runtime = run_scenario("human_intervention")

    assert result.status == OrchestrationStatus.AWAITING_HUMAN_ACTION
    intervention = result.integration_result.execution_result.human_intervention
    assert intervention.checkpoint_reference == "demo-checkpoint-1"
    assert runtime.execution.calls == ["requirement-address-proof", "perform-aadhaar-action"]


def test_execution_failure_is_preserved():
    result, runtime = run_scenario("execution_failure")

    assert result.status == OrchestrationStatus.EXECUTION_FAILED
    assert result.integration_result.execution_result.status.value == "failed"
    assert "failure" in result.integration_result.execution_result.failure_reason.lower()
    assert runtime.execution.calls == ["requirement-address-proof"]


def test_demo_runtime_orchestrator_dynamic_authorization():
    from agents.orchestration.pipeline import OrchestrationRequest
    from agents.utility_based.execution_assistance import ConfirmedExecutionContext, ConfirmedFact, FactStatus
    from demo.runtime import create_demo_orchestrator

    orchestrator = create_demo_orchestrator()
    session_id = "test-aadhaar-address-update-session"
    context = ConfirmedExecutionContext(
        session_id=session_id,
        document_refs=["address-proof-demo"],
        facts={
            "address": ConfirmedFact(
                value="12 Main Street",
                provenance="demo-user-confirmation",
                status=FactStatus.CONFIRMED,
                allowed_for_execution=True,
            )
        },
    )
    request = OrchestrationRequest(
        user_request={
            "session_id": session_id,
            "user_message": "I want to update my Aadhaar address",
            "domain": "aadhaar",
        },
        confirmed_context=context,
    )

    result = orchestrator.run(request)

    # 1. Real WorkflowPlan is generated
    assert result.workflow_plan is not None
    plan = result.workflow_plan

    # 2. Actual step IDs are discovered
    plan_step_ids = [step.step_id for step in plan.steps]
    assert "review-retrieved-evidence" in plan_step_ids
    assert "perform-aadhaar-action" in plan_step_ids

    # 3. Dynamic authorization was created and bound to the plan
    auth = result.integration_result.execution_result
    assert auth is not None

    # 4. Compliance allowed execution without step ID mismatch
    assert result.status == OrchestrationStatus.EXECUTION_COMPLETED
    assert result.integration_result.compliance_decision.allowed is True

    # 5. Proceeds to the mock execution boundary without any external government calls
    assert result.integration_result.execution_result.status.value == "completed"


def test_compliance_adapter_rejects_stale_step_ids():
    from agents.knowledge_based.compliance_validation.schema import ComplianceValidationInput
    from agents.orchestration.integration.compliance_adapter import ComplianceAgentAdapter
    from agents.orchestration.workflow_planning.schema import WorkflowPlan, PlanStep, StepType, StepStatus, PlanStatus
    from demo.run_demo import DemoComplianceFixture, ValidationStatus

    stale_step_ids = ["non-existent-stale-step"]
    adapter = ComplianceAgentAdapter(
        agent=DemoComplianceFixture(ValidationStatus.PASS if hasattr(ValidationStatus, "PASS") else ValidationStatus.WARNING),
        validation_input=ComplianceValidationInput(
            document_type="AADHAAR",
            service_type="aadhaar_update",
            user_information={"address": "12 Main Street"},
            form_data={"address": "12 Main Street"},
            requirements={"required_information": ["address"]},
            confidence={"address": "USER_CONFIRMED"},
        ),
        policy_version="test-policy-v1",
        authorized_step_ids=stale_step_ids,
    )

    dummy_plan = WorkflowPlan(
        planning_request_id="test-plan",
        request_id="test-plan",
        session_id="test-plan",
        service="Aadhaar",
        task="update",
        target="address",
        plan_status=PlanStatus.READY,
        steps=[
            PlanStep(
                step_id="perform-aadhaar-action",
                sequence=1,
                title="Perform action",
                description="Action description",
                step_type=StepType.USER_ACTION,
                status=StepStatus.READY,
            )
        ],
    )

    decision = adapter.validate(dummy_plan)
    assert decision.allowed is False
    assert "Compliance authorized steps absent from the workflow plan" in decision.reason
    assert "non-existent-stale-step" in decision.reason

