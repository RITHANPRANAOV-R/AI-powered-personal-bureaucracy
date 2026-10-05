from __future__ import annotations

import re
from agents.orchestration.workflow_planning.schema import PlanStep, StepStatus, StepType
from agents.utility_based.execution_assistance import (
    AdapterStatus,
    ConfirmedExecutionContext,
    ConfirmedFact,
    FactStatus,
    UIDAIExecutionAdapter,
)


def _sample_context(otp: str | None = None, doc_refs: list[str] | None = None) -> ConfirmedExecutionContext:
    facts = {
        "address": ConfirmedFact(
            value="12 Main Street, Bangalore 560001",
            provenance="user-extracted-doc",
            status=FactStatus.CONFIRMED,
            allowed_for_execution=True,
        )
    }
    if otp is not None:
        facts["aadhaar_otp"] = ConfirmedFact(
            value=otp,
            provenance="user-mobile-otp",
            status=FactStatus.CONFIRMED,
            allowed_for_execution=True,
        )
    return ConfirmedExecutionContext(
        session_id="test-session-123",
        document_refs=doc_refs if doc_refs is not None else ["doc-proof-of-address-1"],
        facts=facts,
    )


def test_uidai_adapter_review_evidence_step():
    adapter = UIDAIExecutionAdapter()
    step = PlanStep(
        step_id="review-retrieved-evidence",
        sequence=1,
        title="Review retrieved Aadhaar evidence",
        description="Review cited UIDAI requirements.",
        step_type=StepType.REVIEW_EVIDENCE,
        status=StepStatus.READY,
    )
    result = adapter.execute_step(step, _sample_context())
    assert result.status == AdapterStatus.COMPLETED
    assert "Reviewed" in result.outcome


def test_uidai_adapter_document_requirement_step_success():
    adapter = UIDAIExecutionAdapter()
    step = PlanStep(
        step_id="requirement-address-proof",
        sequence=2,
        title="Prepare accepted address proof",
        description="Attach valid address proof document.",
        step_type=StepType.PREPARE_DOCUMENT,
        status=StepStatus.READY,
        required_document_refs=["doc-proof-of-address-1"],
    )
    result = adapter.execute_step(step, _sample_context(doc_refs=["doc-proof-of-address-1"]))
    assert result.status == AdapterStatus.COMPLETED
    assert "Supporting documentation verified" in result.outcome


def test_uidai_adapter_document_requirement_step_missing_ref():
    adapter = UIDAIExecutionAdapter()
    step = PlanStep(
        step_id="requirement-address-proof",
        sequence=2,
        title="Prepare accepted address proof",
        description="Attach valid address proof document.",
        step_type=StepType.PREPARE_DOCUMENT,
        status=StepStatus.READY,
        required_document_refs=["doc-proof-of-address-1"],
    )
    result = adapter.execute_step(step, _sample_context(doc_refs=[]))
    assert result.status == AdapterStatus.FAILED
    assert result.error_category == "missing_document"
    assert result.retryable is True


def test_uidai_adapter_portal_action_requires_otp_interruption():
    adapter = UIDAIExecutionAdapter(require_otp=True)
    step = PlanStep(
        step_id="perform-aadhaar-action",
        sequence=3,
        title="Perform Aadhaar address update",
        description="Submit address update to UIDAI SSUP.",
        step_type=StepType.USER_ACTION,
        status=StepStatus.READY,
    )
    result = adapter.execute_step(step, _sample_context(otp=None))
    assert result.status == AdapterStatus.HUMAN_INTERVENTION_REQUIRED
    assert result.human_intervention is not None
    assert result.human_intervention.resumable is True
    assert "OTP" in result.human_intervention.reason
    assert "uidai-otp-test-session-123" == result.human_intervention.checkpoint_reference


def test_uidai_adapter_portal_action_invalid_otp():
    adapter = UIDAIExecutionAdapter(require_otp=True)
    step = PlanStep(
        step_id="perform-aadhaar-action",
        sequence=3,
        title="Perform Aadhaar address update",
        description="Submit address update to UIDAI SSUP.",
        step_type=StepType.USER_ACTION,
        status=StepStatus.READY,
    )
    result = adapter.execute_step(step, _sample_context(otp="1234"))  # only 4 digits
    assert result.status == AdapterStatus.FAILED
    assert result.error_category == "invalid_otp"
    assert "6 digits" in result.outcome


def test_uidai_adapter_portal_action_valid_otp_generates_urn():
    adapter = UIDAIExecutionAdapter(require_otp=True)
    step = PlanStep(
        step_id="perform-aadhaar-action",
        sequence=3,
        title="Perform Aadhaar address update",
        description="Submit address update to UIDAI SSUP.",
        step_type=StepType.USER_ACTION,
        status=StepStatus.READY,
    )
    result = adapter.execute_step(step, _sample_context(otp="482910"))
    assert result.status == AdapterStatus.COMPLETED
    assert result.portal_reference is not None
    assert re.match(r"^\d{4}/\d{5}/\d{5}$", result.portal_reference)
    assert "URN" in result.outcome
    assert "SRN" in result.outcome
