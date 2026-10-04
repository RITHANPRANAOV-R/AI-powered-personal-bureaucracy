from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.knowledge_based.compliance_validation.agent import ComplianceValidationAgent
from agents.knowledge_based.compliance_validation.schema import (
    ComplianceValidationInput,
    ComplianceValidationResult,
    ValidationStatus,
)
from agents.knowledge_based.information_retrieval.schemas import (
    Evidence,
    RetrievalResult,
    RetrievalStatus,
    Source,
    SourceType,
)
from agents.orchestration.integration import (
    ComplianceAgentAdapter,
    ExecutionIntegrationService,
)
from agents.orchestration.intent_understanding import IntentUnderstandingService
from agents.orchestration.monitoring import MonitoringService
from agents.orchestration.pipeline import (
    OrchestrationRequest,
    OrchestrationResult,
    TopLevelOrchestrator,
)
from agents.utility_based.execution_assistance import (
    AdapterResult,
    ConfirmedExecutionContext,
    ConfirmedFact,
    ExecutionAuthorization,
    ExecutionOptions,
    FactStatus,
    HumanIntervention,
    MockExecutionAdapter,
    ResumeCheckpoint,
)
from agents.utility_based.execution_assistance.executor import ExecutionCoordinator


SCENARIOS = (
    "happy_path",
    "missing_information",
    "compliance_warning",
    "compliance_blocked",
    "human_intervention",
    "execution_failure",
)
EXECUTABLE_STEP_IDS = ["requirement-address-proof", "perform-aadhaar-action"]
REVIEW_EVIDENCE_STEP_ID = "review-retrieved-evidence"
APPROVAL_STEP_ID = "review-before-aadhaar-action"


class DemoRetrievalAgent:
    """Offline retrieval boundary returning fixed, evidence-grounded demo data."""

    def __init__(self):
        self.calls = 0

    def retrieve(self, request, user_documents=None):
        self.calls += 1
        source = Source(
            source_id="demo-uidai-source",
            authority="UIDAI",
            domain="aadhaar",
            source_type=SourceType.OFFICIAL_FAQ,
            document_title="Demo Aadhaar address update requirement",
        )
        evidence = Evidence(
            evidence_id="ev-address-proof",
            claim="An address proof is required for the demo Aadhaar address update.",
            passage="Demo evidence: prepare an accepted address proof.",
            source=source,
            grounding_status="verified_grounded",
            metadata={"associated_requirements": ["address-proof"], "category": "document"},
        )
        return RetrievalResult(
            result_id="demo-retrieval-result",
            request_id=request.request_id,
            service="Aadhaar",
            domain="aadhaar",
            retrieval_status=RetrievalStatus.SUCCESS,
            requirements=[{
                "requirement_id": "address-proof",
                "category": "document",
                "description": "Prepare an accepted address proof.",
                "evidence_ids": ["ev-address-proof"],
            }],
            evidence=[evidence],
        )


class DemoComplianceFixture:
    """Offline compliance result fixture for warning and blocked scenarios."""

    def __init__(self, status: ValidationStatus):
        self.status = status
        self.calls = 0

    def run(self, data: ComplianceValidationInput) -> ComplianceValidationResult:
        self.calls += 1
        reason = {
            ValidationStatus.WARNING: "Required compliance information is incomplete.",
            ValidationStatus.BLOCKED: "Compliance policy blocked this demo action.",
        }[self.status]
        return ComplianceValidationResult(
            document_type="AADHAAR",
            service_type="aadhaar_update",
            status=self.status,
            overall_status=self.status,
            next_action=reason,
        )


class DemoResponseGenerator:
    """Offline response-generation boundary; it does not replace the response agent."""

    def __init__(self):
        self.calls = 0
        self.inputs = []

    def generate(self, result):
        self.calls += 1
        self.inputs.append(result)
        return {
            "demo_adapter": True,
            "headline": result.overall_status,
            "summary": result.action_required or "No further demo action is required.",
        }


@dataclass
class DemoRuntime:
    orchestrator: TopLevelOrchestrator
    request: OrchestrationRequest
    retrieval: DemoRetrievalAgent
    execution: MockExecutionAdapter
    response: DemoResponseGenerator
    compliance: Any


def _confirmed_context() -> ConfirmedExecutionContext:
    return ConfirmedExecutionContext(
        session_id="demo-session",
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


def _authorization() -> ExecutionAuthorization:
    now = datetime.now(timezone.utc)
    return ExecutionAuthorization(
        authorization_id="demo-authorization",
        user_id="demo-user",
        session_id="demo-session",
        plan_id="demo-session",
        plan_version=1,
        approved_step_ids=[REVIEW_EVIDENCE_STEP_ID, *EXECUTABLE_STEP_IDS],
        satisfied_approval_step_ids=[APPROVAL_STEP_ID],
        approved_at=now,
        expires_at=now + timedelta(hours=1),
    )


def build_demo(scenario: str) -> DemoRuntime:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'. Choose one of: {', '.join(SCENARIOS)}")

    retrieval = DemoRetrievalAgent()
    response = DemoResponseGenerator()
    outcomes = {}
    if scenario == "human_intervention":
        outcomes["perform-aadhaar-action"] = AdapterResult(
            status="human_intervention_required",
            outcome="Paused for demo human intervention.",
            human_intervention=HumanIntervention(
                reason="Manual verification is required.",
                required_user_action="Complete the manual verification step.",
                checkpoint_reference="demo-checkpoint-1",
            ),
        )
    elif scenario == "execution_failure":
        outcomes["requirement-address-proof"] = AdapterResult(
            status="failed",
            outcome="Deterministic demo execution failure.",
            error_category="demo_failure",
            retryable=False,
        )
    execution = MockExecutionAdapter(outcomes)

    if scenario == "compliance_warning":
        compliance_agent = DemoComplianceFixture(ValidationStatus.WARNING)
    elif scenario == "compliance_blocked":
        compliance_agent = DemoComplianceFixture(ValidationStatus.BLOCKED)
    else:
        compliance_agent = ComplianceValidationAgent()
    compliance_input = ComplianceValidationInput(
        document_type="AADHAAR",
        service_type="aadhaar_update",
        user_information={"address": "12 Main Street"},
        form_data={"address": "12 Main Street"},
        requirements={"required_information": ["address"]},
        confidence={"address": "USER_CONFIRMED"},
    )
    compliance_adapter = ComplianceAgentAdapter(
        agent=compliance_agent,
        validation_input=compliance_input,
        policy_version="demo-compliance-v1",
        authorized_step_ids=list(EXECUTABLE_STEP_IDS),
    )
    integration = ExecutionIntegrationService(
        executor=ExecutionCoordinator(execution),
        compliance_validator=compliance_adapter,
    )
    orchestrator = TopLevelOrchestrator(
        intent_service=IntentUnderstandingService(),
        retrieval_agent=retrieval,
        execution_integration=integration,
        monitoring_service=MonitoringService(),
        response_generator=response,
    )
    message = "Update my Aadhaar address"
    if scenario != "missing_information":
        message = "Update my Aadhaar address to 12 Main Street"
    request = OrchestrationRequest(
        user_request={
            "session_id": "demo-session",
            "user_message": message,
            "domain": "aadhaar",
        },
        execution_authorization=None if scenario == "missing_information" else _authorization(),
        confirmed_context=None if scenario == "missing_information" else _confirmed_context(),
        resume_checkpoint=None if scenario == "missing_information" else ResumeCheckpoint(
            checkpoint_reference="demo-review-checkpoint",
            completed_step_ids=[REVIEW_EVIDENCE_STEP_ID],
            human_action_completed=True,
        ),
    )
    return DemoRuntime(orchestrator, request, retrieval, execution, response, compliance_agent)


def run_scenario(scenario: str) -> tuple[OrchestrationResult, DemoRuntime]:
    runtime = build_demo(scenario)
    return runtime.orchestrator.run(runtime.request), runtime


def format_trace(result: OrchestrationResult) -> str:
    integration = result.integration_result
    compliance_status = "— NOT RUN"
    execution_status = "— NOT RUN"
    if integration is not None:
        if integration.compliance_decision is not None:
            compliance_status = "✓ PASS" if integration.compliance_decision.allowed else "✗ BLOCKED"
        if integration.execution_result is not None:
            execution_status = f"✓ {integration.execution_result.status.value.upper()}"
    lines = [
        f"[1] Intent Understanding       {'✓' if result.intent_result else '✗'}",
        f"[2] Session State              {'✓' if result.session_state else '✗'}",
        f"[3] Information Retrieval      {'✓' if result.retrieval_result else '— NOT RUN'}",
        f"[4] Workflow Planning          {'✓' if result.workflow_plan else '— NOT RUN'}",
        f"[5] Compliance                 {compliance_status}",
        f"[6] Execution                  {execution_status}",
        f"[7] Monitoring/Event           {'✓' if result.session_changes or result.execution_events else '—'}",
        f"[8] Response Generation        {'✓' if result.response_result is not None else '✗'}",
        f"Overall status: {result.status.value}",
    ]
    if result.blocking_reason:
        lines.append(f"Stopped/reason: {result.blocking_reason}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline Aadhaar pipeline demo.")
    parser.add_argument("scenario", nargs="?", default="happy_path", choices=SCENARIOS)
    args = parser.parse_args()
    try:
        result, _ = run_scenario(args.scenario)
    except Exception as error:
        print(f"Demo failed: {error}")
        return 1
    print(format_trace(result))
    print("\nStructured result:")
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    print("\nDEMO ONLY: no real Aadhaar or government action was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
