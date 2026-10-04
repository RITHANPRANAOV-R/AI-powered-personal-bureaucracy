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
