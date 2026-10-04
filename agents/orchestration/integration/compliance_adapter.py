from __future__ import annotations

from typing import Protocol

from agents.knowledge_based.compliance_validation.schema import (
    ComplianceValidationInput,
    ComplianceValidationResult,
    ValidationStatus,
)
from agents.orchestration.workflow_planning.schema import WorkflowPlan
from agents.utility_based.execution_assistance import ComplianceDecision


class ComplianceAgent(Protocol):
    def run(self, data: ComplianceValidationInput) -> ComplianceValidationResult:
        """Run the repository's deterministic compliance validation."""


class ComplianceAgentAdapter:
    """Translate the real compliance agent result into the execution contract."""

    def __init__(
        self,
        agent: ComplianceAgent,
        validation_input: ComplianceValidationInput,
        policy_version: str,
        authorized_step_ids: list[str],
    ):
        self.agent = agent
        self.validation_input = validation_input
        self.policy_version = policy_version
        self.authorized_step_ids = list(authorized_step_ids)

    def validate(self, workflow_plan: WorkflowPlan) -> ComplianceDecision:
        plan_step_ids = {step.step_id for step in workflow_plan.steps}
        unknown_step_ids = set(self.authorized_step_ids) - plan_step_ids
        if not self.authorized_step_ids:
            return ComplianceDecision(
                allowed=False,
                policy_version=self.policy_version,
                reason="Compliance did not provide an explicit authorized step scope.",
            )
        if unknown_step_ids:
            return ComplianceDecision(
                allowed=False,
                policy_version=self.policy_version,
                reason=f"Compliance authorized steps absent from the workflow plan: {sorted(unknown_step_ids)}.",
            )

        result = self.agent.run(self.validation_input)
        allowed = result.overall_status == ValidationStatus.PASS
        reason = result.next_action
        if result.overall_status != ValidationStatus.PASS:
            reason = f"Compliance returned {result.overall_status.value}: {result.next_action}"
        return ComplianceDecision(
            allowed=allowed,
            policy_version=self.policy_version,
            reason=reason,
            authorized_step_ids=list(self.authorized_step_ids) if allowed else [],
        )
