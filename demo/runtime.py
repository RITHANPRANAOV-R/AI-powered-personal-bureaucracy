from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.orchestration.pipeline import OrchestrationRequest, OrchestrationResult
from agents.utility_based.execution_assistance import ExecutionAuthorization, ResumeCheckpoint

from .run_demo import APPROVAL_STEP_ID, EXECUTABLE_STEP_IDS, REVIEW_EVIDENCE_STEP_ID, build_demo


class DemoRuntimeOrchestrator:
    """Local-only wrapper that supplies the demo's explicit synthetic authorization."""

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    def run(self, request: OrchestrationRequest) -> OrchestrationResult:
        if request.confirmed_context is None or request.execution_authorization is not None:
            return self.orchestrator.run(request)
        session_id = request.user_request.session_id
        now = datetime.now(timezone.utc)
        authorized_request = request.model_copy(update={
            "execution_authorization": ExecutionAuthorization(
                authorization_id=f"demo-authorization-{session_id}",
                user_id="demo-user",
                session_id=session_id,
                plan_id=session_id,
                plan_version=1,
                approved_step_ids=[REVIEW_EVIDENCE_STEP_ID, *EXECUTABLE_STEP_IDS],
                satisfied_approval_step_ids=[APPROVAL_STEP_ID],
                approved_at=now,
                expires_at=now + timedelta(hours=1),
            ),
            "resume_checkpoint": ResumeCheckpoint(
                checkpoint_reference=f"demo-review-checkpoint-{session_id}",
                completed_step_ids=[REVIEW_EVIDENCE_STEP_ID],
                human_action_completed=True,
            ),
        })
        return self.orchestrator.run(OrchestrationRequest.model_validate(authorized_request.model_dump(mode="python")))


def create_demo_orchestrator() -> DemoRuntimeOrchestrator:
    """Build the same deterministic composition used by the existing demo."""
    return DemoRuntimeOrchestrator(build_demo("happy_path").orchestrator)
