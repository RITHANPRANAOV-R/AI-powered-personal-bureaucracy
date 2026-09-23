"""Compliance & Validation Agent implementation.

Deterministic policy gatekeeper for checking upstream contracts, evidence provenance,
fact confirmation statuses, dependency graphs, consequential action approvals, credential safety,
and post-execution observations.

Zero generative LLM calls are made in this agent.
"""

from __future__ import annotations

from typing import List, Set

from pydantic import ValidationError

from agents.user_context.schema import FactStatus

from .rules import (
    validate_consequential_actions_and_approvals,
    validate_contract_and_provenance,
    validate_facts_and_dependencies,
    validate_post_execution_observations,
)
from .schema import (
    ComplianceValidationRequest,
    IssueSeverity,
    POLICY_VERSION,
    StepValidationDecision,
    StepValidationResult,
    ValidationDecision,
    ValidationIssue,
    ValidationResult,
    utc_now,
)


class ComplianceValidationError(ValueError):
    """Raised when a compliance request cannot be parsed or initialized."""


class ComplianceValidationAgent:
    """Public deterministic Compliance & Validation Agent."""

    def validate_workflow(
        self, request: ComplianceValidationRequest
    ) -> ValidationResult:
        """
        Public callable for validating a workflow plan and execution context.

        Signature:
            def validate_workflow(request: ComplianceValidationRequest) -> ValidationResult
        """
        try:
            request = ComplianceValidationRequest.model_validate(request)
        except ValidationError as exc:
            raise ComplianceValidationError(f"Invalid ComplianceValidationRequest: {exc}") from exc

        # Execute auditable deterministic rule functions
        provenance_issues, prov_passed_rules = validate_contract_and_provenance(request)
        fact_dag_issues, fact_passed_rules = validate_facts_and_dependencies(request)
        approval_issues, checkpoints, approval_passed_rules = validate_consequential_actions_and_approvals(request)
        obs_issues, obs_passed_rules = validate_post_execution_observations(request)

        all_issues: List[ValidationIssue] = (
            provenance_issues + fact_dag_issues + approval_issues + obs_issues
        )
        all_passed_rules: List[str] = list(
            set(prov_passed_rules + fact_passed_rules + approval_passed_rules + obs_passed_rules)
        )

        plan = request.workflow_plan
        target_steps = (
            [s for s in plan.steps if s.step_id in request.requested_step_ids]
            if request.requested_step_ids
            else plan.steps
        )

        # Build step validation results
        step_results: List[StepValidationResult] = []
        eligible_step_ids: List[str] = []
        blocked_step_ids: List[str] = []

        confirmed_fact_keys = {
            f.key for f in request.profile_context.relevant_facts if f.status == FactStatus.USER_CONFIRMED and f.confirmed_by_user
        }

        for step in target_steps:
            step_issues = [iss for iss in all_issues if step.step_id in iss.affected_step_ids]
            blockers = [iss for iss in step_issues if iss.severity == IssueSeverity.BLOCKER]
            inputs_needed = [iss for iss in step_issues if iss.severity == IssueSeverity.NEEDS_USER_INPUT]

            step_decision = StepValidationDecision.APPROVE
            if blockers or step.status.value in {"blocked", "failed"}:
                step_decision = StepValidationDecision.BLOCK
                blocked_step_ids.append(step.step_id)
            elif inputs_needed or step.status.value == "needs_user_input":
                step_decision = StepValidationDecision.NEEDS_USER_INPUT
                eligible_step_ids.append(step.step_id)
            else:
                eligible_step_ids.append(step.step_id)

            reasons = [iss.message for iss in step_issues]
            if not reasons:
                reasons.append("Step passed all deterministic compliance checks.")

            step_results.append(
                StepValidationResult(
                    step_id=step.step_id,
                    decision=step_decision,
                    passed_rule_ids=[r for r in all_passed_rules if r.startswith("RULE_")],
                    failed_rule_ids=[iss.category.value for iss in step_issues],
                    cited_evidence_ids=list(step.evidence_ids),
                    required_confirmed_fact_keys=[k for k in step.required_fact_keys if k in confirmed_fact_keys],
                    reasons=reasons,
                )
            )

        # Top-level decision
        has_blockers = any(iss.severity == IssueSeverity.BLOCKER for iss in all_issues)
        has_needs_input = any(iss.severity == IssueSeverity.NEEDS_USER_INPUT for iss in all_issues)

        if has_blockers or len(blocked_step_ids) == len(target_steps):
            decision = ValidationDecision.BLOCK
        elif has_needs_input:
            decision = ValidationDecision.NEEDS_USER_INPUT
        else:
            decision = ValidationDecision.APPROVE

        # Eligible for user review means the plan passed core contract & safety checks
        # and may be presented to the user for human review.
        eligible_for_user_review = not has_blockers

        summary_parts = [
            f"Validation decision: {decision.value.upper()}.",
            f"Phase: {request.validation_phase.value}.",
            f"Eligible steps for user review: {len(eligible_step_ids)}/{len(target_steps)}.",
            f"Blocked steps: {len(blocked_step_ids)}.",
            f"Total compliance issues flagged: {len(all_issues)}.",
        ]
        if checkpoints:
            summary_parts.append(f"Required user approval checkpoints: {len(checkpoints)}.")

        return ValidationResult(
            contract_version="1.0",
            validation_request_id=request.validation_request_id,
            request_id=request.intent.request_id,
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            validation_phase=request.validation_phase,
            decision=decision,
            decision_scope=(
                "approve means only 'plan is eligible to be shown for user review'. "
                "It does NOT authorize execution or form submission."
            ),
            eligible_for_user_review=eligible_for_user_review,
            eligible_step_ids=eligible_step_ids,
            blocked_step_ids=blocked_step_ids,
            step_results=step_results,
            issues=all_issues,
            required_user_approvals=checkpoints,
            execution_authorized=False,  # ALWAYS False!
            validated_at=utc_now(),
            policy_version=POLICY_VERSION,
            summary=" ".join(summary_parts),
        )


def validate_workflow(request: ComplianceValidationRequest) -> ValidationResult:
    """Public callable interface for Compliance & Validation Agent."""
    return ComplianceValidationAgent().validate_workflow(request)
