"""CLI and demonstration flow for Execution & Assistance Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

from agents.compliance_validation.schema import (
    StepValidationDecision,
    StepValidationResult,
    UserApprovalCheckpoint,
    ValidationDecision,
    ValidationPhase,
    ValidationResult,
)
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

from .agent import ExecutionAgent, ExecutionAgentError
from .schema import ExecutionRequest, ExecutionResult, UserExecutionApproval


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

SYNTHETIC_CONFIRMED_FACTS = [
    ProfileFact(
        key="full_name",
        value="Priya Nair",
        status=FactStatus.USER_CONFIRMED,
        source_type=FactSourceType.PROFILE,
        source_ref="profile:full_name",
        extracted_at="2026-01-01T00:00:00+00:00",
        confidence=1.0,
        relevant_to="Full legal name for Passport Seva user registration",
        sensitivity=Sensitivity.ORDINARY,
        confirmed_by_user=True,
    ),
    ProfileFact(
        key="email",
        value="priya.nair.demo@example.com",
        status=FactStatus.USER_CONFIRMED,
        source_type=FactSourceType.USER,
        source_ref="user_input",
        extracted_at="2026-09-23T16:00:00+00:00",
        confidence=1.0,
        relevant_to="User confirmed email address for registration",
        sensitivity=Sensitivity.PERSONAL,
        confirmed_by_user=True,
    ),
]

SYNTHETIC_PROFILE = ProfileContextResult(
    contract_version="1.0",
    request_id="demo-passport-register-001",
    intent_request_id="demo-passport-register-001",
    service_name="Passport Seva",
    task_type=TaskType.REGISTER,
    jurisdiction="Tamil Nadu",
    profile_status=ProfileStatus.READY,
    relevant_facts=SYNTHETIC_CONFIRMED_FACTS,
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
    retrieval_status=RetrievalStatus.COMPLETED,
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
            excerpt="Register yourself as new user by creating User Id on Passport Seva portal.",
            content_hash="demo-hash-001",
            relevance_score=0.95,
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
            confidence=0.95,
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
            step_id="user-controlled-portal-action",
            sequence=2,
            title="User-controlled Passport Seva registration",
            description="Perform registration submission on Passport Seva.",
            step_type=StepType.MANUAL_USER_ACTION,
            status=StepStatus.READY,
            depends_on=["review-official-requirements"],
            required_fact_keys=["full_name", "email"],
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

SYNTHETIC_VALIDATION = ValidationResult(
    contract_version="1.0",
    validation_request_id="demo-val-req-001",
    request_id="demo-passport-register-001",
    plan_id="plan-demo-001",
    plan_version=1,
    validation_phase=ValidationPhase.PRE_EXECUTION,
    decision=ValidationDecision.APPROVE,
    decision_scope="approve means only 'plan is eligible to be shown for user review'. It does NOT authorize execution.",
    eligible_for_user_review=True,
    eligible_step_ids=["review-official-requirements", "user-controlled-portal-action"],
    blocked_step_ids=[],
    step_results=[
        StepValidationResult(
            step_id="review-official-requirements",
            decision=StepValidationDecision.APPROVE,
            passed_rule_ids=["RULE_CONTRACT_VERSION_1.0"],
            reasons=["Step passed compliance checks."],
        ),
        StepValidationResult(
            step_id="user-controlled-portal-action",
            decision=StepValidationDecision.APPROVE,
            passed_rule_ids=["RULE_CONTRACT_VERSION_1.0"],
            reasons=["Step passed compliance checks."],
        ),
    ],
    required_user_approvals=[
        UserApprovalCheckpoint(
            approval_id="chk-user-controlled-portal-action",
            step_id="user-controlled-portal-action",
            required_phrase="SUBMIT PASSPORT SEVA REGISTRATION",
            description="Explicit checkpoint for Passport Seva registration",
        )
    ],
    execution_authorized=False,  # ALWAYS False!
    validated_at="2026-09-23T17:10:00+00:00",
    summary="Validation decision: APPROVE. Plan is eligible for user review.",
)

SYNTHETIC_APPROVALS = [
    UserExecutionApproval(
        approval_id="exec-appr-001",
        step_id="review-official-requirements",
        action_scope="step_execution",
        approved_by_user=True,
        approved_at="2026-09-23T17:15:00+00:00",
        approval_method="terminal_prompt",
        exact_approval_phrase="APPROVE STEP review-official-requirements",
    ),
    UserExecutionApproval(
        approval_id="exec-appr-002",
        step_id="user-controlled-portal-action",
        action_scope="step_execution",
        approved_by_user=True,
        approved_at="2026-09-23T17:15:00+00:00",
        approval_method="terminal_prompt",
        exact_approval_phrase="SUBMIT PASSPORT SEVA REGISTRATION",
    ),
]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execution & Assistance Agent CLI. Human-gated Playwright browser automation."
    )
    parser.add_argument("--request-json", help="Path to ExecutionRequest JSON file")
    parser.add_argument("--intent-json", help="Path to IntentResult JSON file")
    parser.add_argument("--profile-json", help="Path to ProfileContextResult JSON file")
    parser.add_argument("--evidence-json", help="Path to RetrievedEvidenceResult JSON file")
    parser.add_argument("--plan-json", help="Path to WorkflowPlan JSON file")
    parser.add_argument("--validation-json", help="Path to ValidationResult JSON file")
    parser.add_argument("--demo", action="store_true", help="Run synthetic Passport Seva demo execution")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode (open browser/inspect form without mutating or submitting)")
    parser.add_argument("--non-interactive", action="store_true", help="Run non-interactively (simulate prompts)")
    parser.add_argument("--json", action="store_true", help="Output full ExecutionResult JSON payload")
    parser.add_argument("--save-json", metavar="PATH", help="Write ExecutionResult JSON to file")
    args = parser.parse_args(argv)

    try:
        request, synthetic = _load_request(args)
    except Exception as exc:
        print(f"Error loading execution request: {exc}", file=sys.stderr)
        return 2

    agent = ExecutionAgent()
    try:
        result = agent.execute_approved_steps(request, interactive=not args.non_interactive)
    except ExecutionAgentError as exc:
        print(f"Execution error: {exc}", file=sys.stderr)
        return 1

    _display_result(result, synthetic=synthetic)

    if args.json:
        print("\n--- ExecutionResult JSON Payload ---")
        print(result.model_dump_json(indent=2))

    if args.save_json:
        Path(args.save_json).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote ExecutionResult JSON to {args.save_json}")

    return 0


def _load_request(args: argparse.Namespace) -> tuple[ExecutionRequest, bool]:
    if args.request_json:
        payload = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
        req = ExecutionRequest.model_validate(payload)
        if args.dry_run:
            req = req.model_copy(update={"dry_run": True})
        return req, False

    if args.intent_json and args.profile_json and args.evidence_json and args.plan_json and args.validation_json:
        intent = IntentResult.model_validate(json.loads(Path(args.intent_json).read_text(encoding="utf-8")))
        profile = ProfileContextResult.model_validate(json.loads(Path(args.profile_json).read_text(encoding="utf-8")))
        evidence = RetrievedEvidenceResult.model_validate(json.loads(Path(args.evidence_json).read_text(encoding="utf-8")))
        plan = WorkflowPlan.model_validate(json.loads(Path(args.plan_json).read_text(encoding="utf-8")))
        val = ValidationResult.model_validate(json.loads(Path(args.validation_json).read_text(encoding="utf-8")))

        req = ExecutionRequest(
            execution_request_id=str(uuid4()),
            request_id=intent.request_id,
            intent=intent,
            profile_context=profile,
            retrieved_evidence=evidence,
            workflow_plan=plan,
            validation_result=val,
            selected_step_ids=val.eligible_step_ids,
            user_approvals=SYNTHETIC_APPROVALS,
            confirmed_facts=[f for f in profile.relevant_facts if f.status == FactStatus.USER_CONFIRMED and f.confirmed_by_user],
            dry_run=args.dry_run,
        )
        return req, False

    if args.demo or not any([args.request_json, args.intent_json]):
        print("Using synthetic Passport Seva upstream contracts for execution demo.")
        req = ExecutionRequest(
            execution_request_id="demo-exec-req-001",
            request_id=SYNTHETIC_INTENT.request_id,
            intent=SYNTHETIC_INTENT,
            profile_context=SYNTHETIC_PROFILE,
            retrieved_evidence=SYNTHETIC_EVIDENCE,
            workflow_plan=SYNTHETIC_PLAN,
            validation_result=SYNTHETIC_VALIDATION,
            selected_step_ids=["review-official-requirements", "user-controlled-portal-action"],
            user_approvals=SYNTHETIC_APPROVALS,
            confirmed_facts=SYNTHETIC_CONFIRMED_FACTS,
            dry_run=args.dry_run,
        )
        return req, True

    print(
        "Provide --request-json, OR (--intent-json, --profile-json, --evidence-json, --plan-json, --validation-json), OR --demo.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _display_result(result: ExecutionResult, synthetic: bool = False) -> None:
    print("\n=== Execution & Assistance Result ===")
    if synthetic:
        print("Data label: SYNTHETIC upstream contracts")
    print(f"execution_request_id: {result.execution_request_id}")
    print(f"request_id:           {result.request_id}")
    print(f"plan_id:              {result.plan_id} v{result.plan_version}")
    print(f"execution_status:     {result.execution_status.value.upper()}")
    print(f"submission_attempted: {result.submission_attempted}")
    print(f"confirmation_observed:{result.confirmation_observed}")
    if result.confirmation_reference:
        print(f"reference:            {result.confirmation_reference}")

    print("\nstep execution results:")
    for step_res in result.step_results:
        print(f"  - [{step_res.step_id}] -> status: {step_res.status.value.upper()}")
        print(f"    summary: {step_res.action_summary}")

    if result.field_actions:
        print("\nfield actions (non-secret values masked):")
        for act in result.field_actions:
            print(f"  - {act.field_label}: outcome={act.outcome} (masked_value={act.masked_value})")

    if result.user_pause_points:
        print("\nuser pause points:")
        for pause in result.user_pause_points:
            print(f"  - [{pause.pause_id}] reason: {pause.reason} (status: {pause.resume_status})")

    if result.portal_observations:
        print("\nportal observations:")
        for obs in result.portal_observations:
            print(f"  - [{obs.observation_id}] {obs.page_title} ({obs.url})")

    if result.warnings:
        print("\nwarnings:")
        for w in result.warnings:
            print(f"  - {w}")

    print(f"\ncompleted_at: {result.completed_at}")


if __name__ == "__main__":
    raise SystemExit(main())
