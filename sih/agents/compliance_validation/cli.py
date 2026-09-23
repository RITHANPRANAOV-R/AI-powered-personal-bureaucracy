"""CLI and demonstration for Compliance & Validation Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

from agents.information_retrieval.schema import (
    EvidenceRecord,
    ProcessingMode,
    RequirementCandidate,
    RequirementSourceStatus,
    RetrievedEvidenceResult,
    RetrievalStatus,
    SearchQuery,
    SourceType,
)
from agents.intent_understanding.schema import Complexity, IntentResult, IntentStatus, TaskType
from agents.user_context.schema import (
    FactSourceType,
    FactStatus,
    ProfileContextResult,
    ProfileFact,
    ProfileStatus,
    Sensitivity,
)
from agents.workflow_planning.schema import (
    EvidenceSupportStatus,
    PlanStep,
    PlanStatus,
    PlanningMode,
    StepStatus,
    StepType,
    WorkflowPlan,
)

from .agent import ComplianceValidationAgent, ComplianceValidationError
from .schema import (
    ComplianceValidationRequest,
    ExecutionObservation,
    UserApprovalRecord,
    ValidationPhase,
    ValidationResult,
)


SYNTHETIC_INTENT = IntentResult(
    contract_version="1.0",
    request_id="demo-passport-register-001",
    original_goal="I am a first-time applicant and need to register on Passport Seva to apply for a new ordinary passport in Tamil Nadu.",
    normalized_goal="I am a first-time applicant and need to register on Passport Seva to apply for a new ordinary passport in Tamil Nadu.",
    service_name="Passport Seva",
    document_type="Passport",
    task_type=TaskType.REGISTER,
    jurisdiction="Tamil Nadu",
    language="English",
    complexity=Complexity.MEDIUM,
    confidence=0.74,
    status=IntentStatus.READY,
)

SYNTHETIC_PROFILE = ProfileContextResult(
    contract_version="1.0",
    request_id="demo-passport-register-001",
    intent_request_id="demo-passport-register-001",
    service_name="Passport Seva",
    task_type=TaskType.REGISTER,
    jurisdiction="Tamil Nadu",
    profile_status=ProfileStatus.PARTIAL,
    relevant_facts=[
        ProfileFact(
            key="full_name",
            value="Priya Nair",
            status=FactStatus.USER_CONFIRMED,
            source_type=FactSourceType.PROFILE,
            source_ref="profile:full_name",
            extracted_at="2026-01-01T00:00:00+00:00",
            confidence=1.0,
            relevant_to="User confirmed personal fact for registration.",
            sensitivity=Sensitivity.ORDINARY,
            confirmed_by_user=True,
        ),
        ProfileFact(
            key="date_of_birth",
            value="1994-03-12",
            status=FactStatus.DOCUMENT_EXTRACTED,
            source_type=FactSourceType.DOCUMENT,
            source_ref="notes.txt",
            extracted_at="2026-09-23T16:00:00+00:00",
            confidence=0.72,
            relevant_to="Document extracted fact; requires user confirmation before execution.",
            sensitivity=Sensitivity.PERSONAL,
            confirmed_by_user=False,
        ),
    ],
    processing_mode=ProcessingMode.DETERMINISTIC,
)

SYNTHETIC_EVIDENCE = RetrievedEvidenceResult(
    contract_version="1.0",
    request_id="demo-retrieval-001",
    intent_request_id="demo-passport-register-001",
    profile_context_request_id="demo-passport-register-001",
    service_name="Passport Seva",
    task_type=TaskType.REGISTER,
    jurisdiction="Tamil Nadu",
    retrieval_status=RetrievalStatus.PARTIAL,
    search_queries=[
        SearchQuery(
            query="Passport Seva official register procedure",
            basis="intent.service_name and intent.task_type",
        )
    ],
    evidence=[
        EvidenceRecord(
            evidence_id="ev-001",
            source_title="Steps to apply for passport services",
            source_url="https://www.passportindia.gov.in/AppOnlineProject/pdf/steps_to_apply_for_passport_services.pdf",
            source_host="www.passportindia.gov.in",
            source_type=SourceType.OFFICIAL_PDF,
            retrieved_at="2026-09-23T16:50:00+00:00",
            section_heading="Steps to Apply for Passport Services",
            excerpt="Register yourself as new user by creating User Id. Provide User Id details and click Register.",
            content_hash="demo-hash-001",
            relevance_score=0.92,
            supports=["req-001"],
        )
    ],
    requirements_found=[
        RequirementCandidate(
            requirement_id="req-001",
            statement="Register yourself as new user by creating User Id on Passport Seva.",
            evidence_ids=["ev-001"],
            jurisdiction_scope="Tamil Nadu",
            source_status=RequirementSourceStatus.OFFICIAL_CURRENT_CHECKED,
            confidence=0.9,
        )
    ],
    processing_mode=ProcessingMode.DETERMINISTIC,
)

SYNTHETIC_PLAN = WorkflowPlan(
    contract_version="1.0",
    planning_request_id="demo-plan-001",
    request_id="demo-passport-register-001",
    service_name="Passport Seva",
    document_type="Passport",
    task_type=TaskType.REGISTER,
    jurisdiction="Tamil Nadu",
    language="English",
    plan_id="plan-demo-001",
    plan_version=1,
    plan_status=PlanStatus.READY,
    goal_summary="Register on Passport Seva in Tamil Nadu",
    steps=[
        PlanStep(
            step_id="review-official-requirements",
            sequence=1,
            title="Review official requirements",
            description="Review official Passport Seva registration requirements.",
            step_type=StepType.REVIEW_REQUIREMENTS,
            status=StepStatus.READY,
            evidence_ids=["ev-001"],
            evidence_status=EvidenceSupportStatus.SUPPORTED,
        ),
        PlanStep(
            step_id="confirm-unconfirmed-profile-facts",
            sequence=2,
            title="Confirm unconfirmed personal facts",
            description="Confirm date_of_birth which is currently document_extracted.",
            step_type=StepType.VERIFY_INFORMATION,
            status=StepStatus.NEEDS_USER_INPUT,
            depends_on=["review-official-requirements"],
            required_fact_keys=["date_of_birth"],
            requires_user_action=True,
        ),
        PlanStep(
            step_id="human-approval-before-portal",
            sequence=3,
            title="Explicit approval before portal action",
            description="Pause for explicit user checkpoint before portal registration.",
            step_type=StepType.HUMAN_APPROVAL,
            status=StepStatus.NOT_STARTED,
            depends_on=["confirm-unconfirmed-profile-facts"],
            requires_user_action=True,
            requires_explicit_approval=True,
            consequential_action=True,
        ),
        PlanStep(
            step_id="user-controlled-portal-action",
            sequence=4,
            title="User-controlled Passport Seva registration",
            description="Perform registration submission on Passport Seva.",
            step_type=StepType.MANUAL_USER_ACTION,
            status=StepStatus.NOT_STARTED,
            depends_on=["human-approval-before-portal"],
            required_fact_keys=["full_name"],
            evidence_ids=["ev-001"],
            evidence_status=EvidenceSupportStatus.SUPPORTED,
            requires_user_action=True,
            requires_explicit_approval=True,
            consequential_action=True,
        ),
    ],
    human_approval_points=[],
    created_at="2026-09-23T17:00:00+00:00",
    planning_mode=PlanningMode.DETERMINISTIC_FALLBACK,
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compliance & Validation Agent CLI. Deterministic policy gatekeeper."
    )
    parser.add_argument("--request-json", help="Path to ComplianceValidationRequest JSON file")
    parser.add_argument("--intent-json", help="Path to IntentResult JSON file")
    parser.add_argument("--profile-json", help="Path to ProfileContextResult JSON file")
    parser.add_argument("--evidence-json", help="Path to RetrievedEvidenceResult JSON file")
    parser.add_argument("--plan-json", help="Path to WorkflowPlan JSON file")
    parser.add_argument("--demo", action="store_true", help="Run validation using synthetic Passport Seva demo data")
    parser.add_argument("--phase", choices=["pre_execution", "post_execution"], default="pre_execution", help="Validation phase")
    parser.add_argument("--json", action="store_true", help="Output full ValidationResult JSON payload")
    parser.add_argument("--save-json", metavar="PATH", help="Write ValidationResult JSON to file")
    args = parser.parse_args(argv)

    try:
        request, synthetic = _load_request(args)
    except Exception as exc:
        print(f"Error loading validation request: {exc}", file=sys.stderr)
        return 2

    agent = ComplianceValidationAgent()
    try:
        result = agent.validate_workflow(request)
    except ComplianceValidationError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 1

    _display_result(result, synthetic=synthetic)

    if args.json:
        print("\n--- ValidationResult JSON Payload ---")
        print(result.model_dump_json(indent=2))

    if args.save_json:
        Path(args.save_json).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote ValidationResult JSON to {args.save_json}")

    return 0


def _load_request(args: argparse.Namespace) -> tuple[ComplianceValidationRequest, bool]:
    if args.request_json:
        payload = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
        return ComplianceValidationRequest.model_validate(payload), False

    if args.intent_json and args.profile_json and args.evidence_json and args.plan_json:
        intent = IntentResult.model_validate(json.loads(Path(args.intent_json).read_text(encoding="utf-8")))
        profile = ProfileContextResult.model_validate(json.loads(Path(args.profile_json).read_text(encoding="utf-8")))
        evidence = RetrievedEvidenceResult.model_validate(json.loads(Path(args.evidence_json).read_text(encoding="utf-8")))
        plan = WorkflowPlan.model_validate(json.loads(Path(args.plan_json).read_text(encoding="utf-8")))

        req = ComplianceValidationRequest(
            validation_request_id=str(uuid4()),
            validation_phase=ValidationPhase(args.phase),
            intent=intent,
            profile_context=profile,
            retrieved_evidence=evidence,
            workflow_plan=plan,
        )
        return req, False

    if args.demo or not any([args.request_json, args.intent_json]):
        print("Using synthetic Passport Seva upstream contracts for compliance demo.")
        req = ComplianceValidationRequest(
            validation_request_id="demo-val-req-001",
            validation_phase=ValidationPhase(args.phase),
            intent=SYNTHETIC_INTENT,
            profile_context=SYNTHETIC_PROFILE,
            retrieved_evidence=SYNTHETIC_EVIDENCE,
            workflow_plan=SYNTHETIC_PLAN,
        )
        return req, True

    print(
        "Provide --request-json, OR (--intent-json, --profile-json, --evidence-json, --plan-json), OR --demo.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _display_result(result: ValidationResult, synthetic: bool = False) -> None:
    print("\n=== Compliance & Validation Result ===")
    if synthetic:
        print("Data label: SYNTHETIC upstream contracts")
    print(f"validation_request_id: {result.validation_request_id}")
    print(f"request_id:            {result.request_id}")
    print(f"plan_id:               {result.plan_id} v{result.plan_version}")
    print(f"phase:                 {result.validation_phase.value}")
    print(f"decision:              {result.decision.value.upper()}")
    print(f"decision_scope:        {result.decision_scope}")
    print(f"eligible_for_review:   {result.eligible_for_user_review}")
    print(f"execution_authorized:  {result.execution_authorized} (ALWAYS False)")
    print(f"eligible_steps:        {result.eligible_step_ids}")
    print(f"blocked_steps:         {result.blocked_step_ids}")
    print(f"summary:               {result.summary}")

    print("\nstep validation results:")
    for step_res in result.step_results:
        print(f"  - [{step_res.step_id}] -> decision: {step_res.decision.value.upper()}")
        if step_res.reasons:
            for r in step_res.reasons:
                print(f"      reason: {r}")

    if result.issues:
        print("\ncompliance issues:")
        for issue in result.issues:
            print(f"  - [{issue.severity.value.upper()}] {issue.category.value}: {issue.message}")
            print(f"    required resolution: {issue.required_resolution}")

    if result.required_user_approvals:
        print("\nrequired user approval checkpoints:")
        for chk in result.required_user_approvals:
            print(f"  - step '{chk.step_id}' requires exact phrase: '{chk.required_phrase}'")

    print(f"\nvalidated_at: {result.validated_at}")


if __name__ == "__main__":
    raise SystemExit(main())
