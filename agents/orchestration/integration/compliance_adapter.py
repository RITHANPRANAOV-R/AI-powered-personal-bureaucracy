from __future__ import annotations

from typing import Optional, Protocol

from agents.knowledge_based.compliance_validation.schema import (
    ComplianceValidationInput,
    ComplianceValidationResult,
    ConfidenceLevel,
    ValidationStatus,
)
from agents.orchestration.workflow_planning.schema import WorkflowPlan
from agents.utility_based.execution_assistance import (
    ComplianceDecision,
    ConfirmedExecutionContext,
)


class ComplianceAgent(Protocol):
    def run(self, data: ComplianceValidationInput) -> ComplianceValidationResult:
        """Run the repository's deterministic compliance validation."""


class ComplianceAgentAdapter:
    """Translate the real compliance agent result into the execution contract."""

    def __init__(
        self,
        agent: ComplianceAgent,
        validation_input: Optional[ComplianceValidationInput] = None,
        policy_version: str = "uidai-compliance-v1",
        authorized_step_ids: list[str] | None = None,
    ):
        self.agent = agent
        self.validation_input = validation_input
        self.policy_version = policy_version
        self.authorized_step_ids = list(authorized_step_ids) if authorized_step_ids is not None else None

    def validate(
        self,
        workflow_plan: WorkflowPlan,
        confirmed_context: Optional[ConfirmedExecutionContext] = None,
    ) -> ComplianceDecision:
        from agents.orchestration.workflow_planning.schema import StepType

        plan_step_ids = {step.step_id for step in workflow_plan.steps}
        if self.authorized_step_ids is not None:
            if not self.authorized_step_ids:
                return ComplianceDecision(
                    allowed=False,
                    policy_version=self.policy_version,
                    reason="Compliance did not provide an explicit authorized step scope.",
                )
            unknown_step_ids = set(self.authorized_step_ids) - plan_step_ids
            if unknown_step_ids:
                return ComplianceDecision(
                    allowed=False,
                    policy_version=self.policy_version,
                    reason=f"Compliance authorized steps absent from the workflow plan: {sorted(unknown_step_ids)}.",
                )
            effective_authorized_step_ids = list(self.authorized_step_ids)
        else:
            executable_steps = [
                step.step_id
                for step in workflow_plan.steps
                if step.step_type in {
                    StepType.PREPARE_DOCUMENT,
                    StepType.PREPARE_INFORMATION,
                    StepType.USER_ACTION,
                }
            ]
            if not executable_steps:
                return ComplianceDecision(
                    allowed=False,
                    policy_version=self.policy_version,
                    reason="Compliance did not find any executable steps in the workflow plan.",
                )
            effective_authorized_step_ids = executable_steps

        val_input = self.validation_input
        if val_input is None:
            val_input = self._build_dynamic_input(workflow_plan, confirmed_context)

        result = self.agent.run(val_input)
        allowed = result.overall_status == ValidationStatus.PASS
        reason = result.next_action
        if result.overall_status != ValidationStatus.PASS:
            reason = f"Compliance returned {result.overall_status.value}: {result.next_action}"
        return ComplianceDecision(
            allowed=allowed,
            policy_version=self.policy_version,
            reason=reason,
            authorized_step_ids=effective_authorized_step_ids if allowed else [],
        )

    @staticmethod
    def _build_dynamic_input(
        workflow_plan: WorkflowPlan,
        confirmed_context: Optional[ConfirmedExecutionContext],
    ) -> ComplianceValidationInput:
        user_info: dict[str, object] = {}
        form_data: dict[str, object] = {}
        confidence: dict[str, ConfidenceLevel] = {}
        documents: dict[str, object] = {}

        required_info: list[str] = []
        required_docs: list[str] = []
        for step in workflow_plan.steps:
            required_info.extend(step.required_fact_keys)
            required_docs.extend(step.required_document_refs)

        # Deduplicate while preserving order
        unique_req_info = list(dict.fromkeys(required_info))
        unique_req_docs = list(dict.fromkeys(required_docs))

        if confirmed_context is not None:
            for key, fact in confirmed_context.facts.items():
                user_info[key] = fact.value
                form_data[key] = fact.value
                confidence[key] = ConfidenceLevel.USER_CONFIRMED

            # Alias demographic keys for compliance validation
            if "existing_address" in user_info and "address" not in user_info:
                user_info["address"] = user_info["existing_address"]
                form_data["address"] = form_data["existing_address"]
                confidence["address"] = ConfidenceLevel.USER_CONFIRMED
            elif "address" in user_info and "existing_address" not in user_info:
                user_info["existing_address"] = user_info["address"]
                form_data["existing_address"] = form_data["address"]
                confidence["existing_address"] = ConfidenceLevel.USER_CONFIRMED

            if "date_of_birth" in user_info and "dob" not in user_info:
                user_info["dob"] = user_info["date_of_birth"]
                form_data["dob"] = form_data["date_of_birth"]
                confidence["dob"] = ConfidenceLevel.USER_CONFIRMED

            for doc_ref in confirmed_context.document_refs:
                documents[doc_ref] = {"readable": True, "valid": True}
                for req_doc in unique_req_docs:
                    if req_doc in doc_ref or doc_ref in req_doc or "proof" in req_doc or "doc" in req_doc:
                        documents[req_doc] = {"readable": True, "valid": True}
            if not documents and confirmed_context.document_refs:
                for req_doc in unique_req_docs:
                    documents[req_doc] = {"readable": True, "valid": True}

        doc_type = workflow_plan.domain.upper() if workflow_plan.domain else "AADHAAR"
        service_type = workflow_plan.task if workflow_plan.task else "aadhaar_update"

        return ComplianceValidationInput(
            document_type=doc_type,
            service_type=service_type,
            user_information=user_info,
            form_data=form_data,
            documents=documents,
            requirements={
                "service_type": service_type,
                "document_type": doc_type,
                "required_information": unique_req_info,
                "required_documents": unique_req_docs,
            },
            confidence=confidence,
        )
