from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.knowledge_based.compliance_validation.agent import ComplianceValidationAgent
from agents.knowledge_based.information_retrieval.schemas import (
    Evidence,
    RetrievalResult,
    RetrievalStatus,
    Source,
    SourceType,
)
from agents.orchestration.intent_understanding.schemas import UserRequestInput
from agents.orchestration.pipeline import (
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStatus,
    create_uidai_orchestrator,
)
from agents.orchestration.workflow_planning.schema import StepType
from agents.response_generation.schema import CitizenResponse
from agents.utility_based.execution_assistance import (
    ConfirmedExecutionContext,
    ConfirmedFact,
    ExecutionAuthorization,
    FactStatus,
    ResumeCheckpoint,
    UIDAIExecutionAdapter,
)


class MockUIDAIRetrievalAgent:
    """Provides grounded UIDAI requirements for offline testing."""

    def retrieve(self, request, user_documents=None):
        source = Source(
            source_id="uidai-official-faq",
            authority="UIDAI",
            domain="aadhaar",
            source_type=SourceType.OFFICIAL_FAQ,
            document_title="UIDAI Address Update Guidelines",
        )
        evidence = Evidence(
            evidence_id="ev-uidai-address-proof",
            claim="Valid address proof required for online address update in UIDAI portal.",
            passage="Standard list of accepted Proof of Address (PoA) documents.",
            source=source,
            grounding_status="verified_grounded",
            metadata={"category": "document", "associated_requirements": ["address-proof"]},
        )
        return RetrievalResult(
            result_id=f"retrieval-{request.request_id}",
            request_id=request.request_id,
            service="Aadhaar",
            domain="aadhaar",
            retrieval_status=RetrievalStatus.SUCCESS,
            requirements=[{
                "requirement_id": "address-proof",
                "category": "document",
                "description": "Upload a valid Proof of Address document.",
                "evidence_ids": ["ev-uidai-address-proof"],
            }],
            evidence=[evidence],
        )


def _build_context(session_id: str, otp: str | None = None) -> ConfirmedExecutionContext:
    facts = {
        "address": ConfirmedFact(
            value="12 Main Street, Bangalore 560001",
            provenance="ocr-user-confirmed",
            status=FactStatus.CONFIRMED,
            allowed_for_execution=True,
        )
    }
    if otp:
        facts["aadhaar_otp"] = ConfirmedFact(
            value=otp,
            provenance="user-entered-otp",
            status=FactStatus.CONFIRMED,
            allowed_for_execution=True,
        )
    return ConfirmedExecutionContext(
        session_id=session_id,
        document_refs=["address-proof-doc-1"],
        facts=facts,
    )


def _build_authorization(session_id: str, plan) -> tuple[ExecutionAuthorization, ResumeCheckpoint]:
    now = datetime.now(timezone.utc)
    all_step_ids = [step.step_id for step in plan.steps]
    approval_ids = [step.step_id for step in plan.steps if step.step_type == StepType.HUMAN_APPROVAL or step.requires_explicit_approval]
    review_ids = [step.step_id for step in plan.steps if step.step_type == StepType.REVIEW_EVIDENCE]

    auth = ExecutionAuthorization(
        authorization_id=f"auth-{session_id}",
        user_id="citizen-user-1",
        session_id=session_id,
        plan_id=plan.request_id,
        plan_version=plan.plan_version,
        approved_step_ids=all_step_ids,
        satisfied_approval_step_ids=approval_ids,
        approved_at=now,
        expires_at=now + timedelta(hours=1),
    )
    checkpoint = ResumeCheckpoint(
        checkpoint_reference=f"review-chk-{session_id}",
        completed_step_ids=review_ids,
        human_action_completed=True,
    )
    return auth, checkpoint


def test_uidai_flow_requires_otp_interruption():
    orchestrator = create_uidai_orchestrator(
        require_otp=True,
        retrieval_agent=MockUIDAIRetrievalAgent(),
    )
    session_id = "session-uidai-001"
    initial_request = OrchestrationRequest(
        user_request=UserRequestInput(
            session_id=session_id,
            user_message="Update my Aadhaar address to 12 Main Street, Bangalore 560001",
            domain="aadhaar",
        ),
        confirmed_context=_build_context(session_id, otp=None),
    )

    # First pass without authorization -> pipeline creates plan
    res_plan = orchestrator.run(initial_request)
    assert res_plan.workflow_plan is not None

    # Second pass with authorization, awaiting OTP
    auth, checkpoint = _build_authorization(session_id, res_plan.workflow_plan)
    authorized_request = initial_request.model_copy(update={
        "execution_authorization": auth,
        "resume_checkpoint": checkpoint,
    })
    res_exec = orchestrator.run(authorized_request)

    assert res_exec.status == OrchestrationStatus.AWAITING_HUMAN_ACTION
    assert res_exec.integration_result is not None
    assert res_exec.integration_result.execution_result.human_intervention is not None
    assert "OTP" in res_exec.integration_result.execution_result.human_intervention.reason
    assert isinstance(res_exec.response_result, CitizenResponse)
    assert "Action Required" in res_exec.response_result.headline


def test_uidai_flow_resumes_with_otp_and_completes_with_urn():
    orchestrator = create_uidai_orchestrator(
        require_otp=True,
        retrieval_agent=MockUIDAIRetrievalAgent(),
    )
    session_id = "session-uidai-002"
    user_req = UserRequestInput(
        session_id=session_id,
        user_message="Update my Aadhaar address to 12 Main Street, Bangalore 560001",
        domain="aadhaar",
    )
    context_with_otp = _build_context(session_id, otp="782341")

    # Get plan first
    res_plan = orchestrator.run(OrchestrationRequest(
        user_request=user_req,
        confirmed_context=context_with_otp,
    ))
    auth, checkpoint = _build_authorization(session_id, res_plan.workflow_plan)

    request_with_otp = OrchestrationRequest(
        user_request=user_req,
        confirmed_context=context_with_otp,
        execution_authorization=auth,
        resume_checkpoint=checkpoint,
    )
    res_completed = orchestrator.run(request_with_otp)

    assert res_completed.status == OrchestrationStatus.EXECUTION_COMPLETED
    assert res_completed.integration_result is not None
    assert res_completed.integration_result.execution_result is not None
    step_results = res_completed.integration_result.execution_result.step_results
    assert len(step_results) > 0

    # Verify URN is in terminal step portal reference
    terminal_step = step_results[-1]
    assert terminal_step.portal_reference is not None
    assert "/" in terminal_step.portal_reference
    assert "URN" in terminal_step.outcome

    # Verify response generator formatted markdown
    assert isinstance(res_completed.response_result, CitizenResponse)
    assert "Completed" in res_completed.response_result.headline
    assert "URN" in res_completed.response_result.formatted_markdown or "processed" in res_completed.response_result.summary
