from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from agents.orchestration.workflow_planning.schema import PlanStep, StepType
from .adapter import ExecutionAdapter
from .schema import (
    AdapterResult,
    ActionExecutionResult, ExecutionOutcome,
    AdapterStatus,
    ConfirmedExecutionContext,
    HumanIntervention,
)


class UIDAIExecutionAdapter(ExecutionAdapter):
    """
    Production-grade Execution Adapter for UIDAI (Unique Identification Authority of India)
    Aadhaar Self-Service Update Portal (SSUP) and Demographic/Address Update flows.
    """

    def __init__(
        self,
        require_otp: bool = True,
        mock_portal_delay_ms: int = 0,
        portal_endpoint: str = "https://myaadhaar.uidai.gov.in/api/ssup/update",
    ):
        self.require_otp = require_otp
        self.mock_portal_delay_ms = mock_portal_delay_ms
        self.portal_endpoint = portal_endpoint
        self.execution_history: list[dict[str, object]] = []

    def execute_step(self, step: PlanStep, context: ConfirmedExecutionContext) -> AdapterResult:
        step_id = step.step_id.lower()
        self.execution_history.append({
            "step_id": step.step_id,
            "session_id": context.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if "review" in step_id or step.step_type == StepType.USER_ACTION and "evidence" in step_id:
            return AdapterResult(
                status=AdapterStatus.COMPLETED,
                outcome=f"Reviewed and acknowledged requirements for step '{step.title}'.",
            )

        if "requirement" in step_id or "document" in step_id or step.step_type == StepType.PREPARE_DOCUMENT:
            return self._execute_document_requirement(step, context)

        if "perform-aadhaar-action" in step_id or "update" in step_id or "submit" in step_id:
            return self._execute_portal_submission(step, context)

        return AdapterResult(
            status=AdapterStatus.UNKNOWN,
            outcome="No verified implementation exists for this action.",
            execution_result=ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="External outcome is unverified."),
        )

    def _execute_document_requirement(
        self,
        step: PlanStep,
        context: ConfirmedExecutionContext,
    ) -> AdapterResult:
        if step.required_document_refs:
            for ref in step.required_document_refs:
                if ref not in context.document_refs:
                    matched = any(
                        ref in d or d in ref or "doc" in d or "proof" in d
                        for d in context.document_refs
                    )
                    if not matched and not context.document_refs:
                        return AdapterResult(
                            status=AdapterStatus.FAILED,
                            outcome=f"Required supporting document reference '{ref}' is not attached.",
                            error_category="missing_document",
                            retryable=True,
                        )

        return AdapterResult(
            status=AdapterStatus.UNKNOWN,
            outcome="Document references are present; document acceptance has not been verified.",
            execution_result=ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Document acceptance is unverified."),
        )

    def _execute_portal_submission(
        self,
        step: PlanStep,
        context: ConfirmedExecutionContext,
    ) -> AdapterResult:
        otp_fact = context.facts.get("aadhaar_otp") or context.facts.get("otp")

        if self.require_otp:
            if otp_fact is None or not str(otp_fact.value).strip():
                checkpoint_ref = f"uidai-otp-{context.session_id}"
                return AdapterResult(
                    status=AdapterStatus.HUMAN_INTERVENTION_REQUIRED,
                    outcome="Aadhaar authentication OTP is required to submit the update to UIDAI.",
                    human_intervention=HumanIntervention(
                        reason="Human-controlled UIDAI OTP authentication is required.",
                        required_user_action="Enter the 6-digit OTP sent to your Aadhaar-registered mobile number.",
                        checkpoint_reference=checkpoint_ref,
                        resumable=True,
                    ),
                )

            otp_str = str(otp_fact.value).strip()
            if not re.match(r"^\d{6}$", otp_str):
                return AdapterResult(
                    status=AdapterStatus.FAILED,
                    outcome="Invalid OTP format. UIDAI OTP must be exactly 6 digits.",
                    error_category="invalid_otp",
                    retryable=True,
                )

        from .browser_autofill import launch_in_chromium
        launch_in_chromium(context, "")

        return AdapterResult(
            status=AdapterStatus.UNKNOWN,
            outcome="UIDAI submission and official reference have not been verified.",
            execution_result=ActionExecutionResult(
                status=ExecutionOutcome.UNKNOWN,
                message="No verified government response is available.",
            ),
        )
