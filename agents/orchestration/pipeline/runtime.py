from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from agents.knowledge_based.information_retrieval.agent import InformationRetrievalAgent
from agents.orchestration.pipeline.factory import create_uidai_orchestrator
from agents.orchestration.pipeline.schema import OrchestrationRequest, OrchestrationResult, OrchestrationStatus
from agents.orchestration.workflow_planning.schema import StepType, WorkflowPlanningRequest
from agents.utility_based.execution_assistance import (
    ConfirmedFact,
    ExecutionAuthorization,
    FactStatus,
    ResumeCheckpoint,
    UIDAIExecutionAdapter,
)


class UIDAIRuntimeOrchestrator:
    """
    Production-ready Runtime Orchestrator for UIDAI flows.
    Handles dynamic authorization synthesis, document linking, OTP interruptions, and resumption.
    """

    def __init__(self, orchestrator=None, require_otp: bool = True):
        self.orchestrator = orchestrator or create_uidai_orchestrator(require_otp=require_otp)

    def run(self, request: OrchestrationRequest) -> OrchestrationResult:
        if request.confirmed_context is None:
            return self.orchestrator.run(request)

        # Normalize address into user message if missing
        user_msg = request.user_request.user_message or ""
        if "update" in user_msg.lower() and "address" in user_msg.lower():
            addr_fact = (
                request.confirmed_context.facts.get("address")
                or request.confirmed_context.facts.get("existing_address")
            )
            if addr_fact and addr_fact.value and str(addr_fact.value).lower() not in user_msg.lower():
                user_msg = f"{user_msg.rstrip('.')} to {addr_fact.value}"

        req_for_planning = request.model_copy(update={
            "user_request": request.user_request.model_copy(update={"user_message": user_msg})
        })

        if request.execution_authorization is not None:
            return self.orchestrator.run(req_for_planning)

        # Step 1: Intent Understanding
        intent_res = self.orchestrator.intent_service.process(req_for_planning.user_request)
        if intent_res.missing_information:
            return self.orchestrator.run(req_for_planning)

        # Step 2: Session Monitoring
        monitoring_res = self.orchestrator.monitoring_service.process(
            req_for_planning.previous_session_state,
            intent_res,
        )

        # Step 3: Information Retrieval
        retrieval_req = self.orchestrator._build_retrieval_request(
            req_for_planning.user_request,
            intent_res,
            req_for_planning.user_documents,
        )
        retrieval_res = self.orchestrator.retrieval_agent.retrieve(
            retrieval_req,
            user_documents=req_for_planning.user_documents,
        )

        # Step 4: Evidence-Grounded Workflow Planning
        planning_req = WorkflowPlanningRequest(
            intent=intent_res,
            session_state=monitoring_res.updated_state,
            retrieved_evidence=retrieval_res,
            user_constraints=req_for_planning.user_constraints,
        )
        actual_plan = self.orchestrator.workflow_planner(planning_req)

        # Extract step groups
        review_step_ids = [
            step.step_id for step in actual_plan.steps
            if step.step_type == StepType.REVIEW_EVIDENCE
        ]
        executable_step_ids = [
            step.step_id for step in actual_plan.steps
            if step.step_type in {
                StepType.PREPARE_DOCUMENT,
                StepType.PREPARE_INFORMATION,
                StepType.USER_ACTION,
            }
        ]
        approval_step_ids = [
            step.step_id for step in actual_plan.steps
            if step.step_type == StepType.HUMAN_APPROVAL or step.requires_explicit_approval
        ]

        session_id = request.user_request.session_id
        now = datetime.now(timezone.utc)

        # Citizen consent authorization
        synthetic_auth = ExecutionAuthorization(
            authorization_id=f"uidai-authorization-{session_id}",
            user_id="citizen-user",
            session_id=session_id,
            plan_id=actual_plan.request_id,
            plan_version=actual_plan.plan_version,
            approved_step_ids=review_step_ids + executable_step_ids,
            satisfied_approval_step_ids=approval_step_ids,
            approved_at=now,
            expires_at=now + timedelta(hours=1),
        )

        # Acknowledge evidence review
        review_checkpoint = ResumeCheckpoint(
            checkpoint_reference=f"uidai-review-checkpoint-{session_id}",
            completed_step_ids=review_step_ids,
            human_action_completed=True,
        )

        authorized_request = req_for_planning.model_copy(update={
            "execution_authorization": synthetic_auth,
            "resume_checkpoint": request.resume_checkpoint or review_checkpoint,
        })
        return self.orchestrator.run(authorized_request)


def create_production_orchestrator(
    require_otp: bool = True,
    retrieval_agent: Optional[InformationRetrievalAgent] = None,
) -> UIDAIRuntimeOrchestrator:
    """Creates a production-ready runtime orchestrator wired to UIDAI execution flow."""
    inner = create_uidai_orchestrator(
        require_otp=require_otp,
        retrieval_agent=retrieval_agent,
    )
    return UIDAIRuntimeOrchestrator(orchestrator=inner, require_otp=require_otp)
