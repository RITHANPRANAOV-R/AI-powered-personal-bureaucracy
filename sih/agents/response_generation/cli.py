"""CLI and demonstration flow for Response Generation Agent."""

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
from agents.execution_assistance.schema import (
    ExecutionResult,
    ExecutionStatus,
    FieldActionRecord,
    PortalObservation,
    StepExecutionResult,
    StepExecutionStatus,
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
from agents.monitoring_update.schema import (
    EventSourceType,
    MonitoringResult,
    MonitoringStatus,
    StatusEvent,
    StepMonitoringStatus,
)
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

from .agent import ResponseGenerationAgent, ResponseGenerationError
from .schema import DetailLevel, ResponseGenerationRequest


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
    profile_status=ProfileStatus.READY,
    relevant_facts=[
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
        )
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
            status=StepStatus.COMPLETED,
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
            required_fact_keys=["full_name"],
            evidence_ids=["ev-001"],
            evidence_status=EvidenceSupportStatus.SUPPORTED,
            requires_user_action=True,
            requires_explicit_approval=True,
            consequential_action=True,
        ),
    ],
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
    execution_authorized=False,
    validated_at="2026-09-23T17:10:00+00:00",
    summary="Validation decision: APPROVE.",
)

SYNTHETIC_MONITORING = MonitoringResult(
    contract_version="1.0",
    monitoring_request_id="demo-mon-req-001",
    request_id="demo-passport-register-001",
    plan_id="plan-demo-001",
    plan_version=1,
    execution_request_id="demo-exec-req-001",
    monitoring_status=MonitoringStatus.NEEDS_USER_UPDATE,
    workflow_status="needs_user_input",
    step_statuses=[
        StepMonitoringStatus(
            step_id="review-official-requirements",
            current_status="completed",
            last_updated_at="2026-09-23T18:00:00+00:00",
            last_source_type=EventSourceType.PLAN,
            last_event_id="evt-001",
        ),
        StepMonitoringStatus(
            step_id="user-controlled-portal-action",
            current_status="needs_user_input",
            last_updated_at="2026-09-23T18:00:00+00:00",
            last_source_type=EventSourceType.VALIDATION_AGENT,
            last_event_id="evt-002",
        ),
    ],
    updated_at="2026-09-23T18:00:00+00:00",
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Response Generation Agent CLI. Formulates citizen-friendly Markdown & JSON response."
    )
    parser.add_argument("--request-json", help="Path to ResponseGenerationRequest JSON file")
    parser.add_argument("--intent-json", help="Path to IntentResult JSON file")
    parser.add_argument("--profile-json", help="Path to ProfileContextResult JSON file")
    parser.add_argument("--evidence-json", help="Path to RetrievedEvidenceResult JSON file")
    parser.add_argument("--plan-json", help="Path to WorkflowPlan JSON file")
    parser.add_argument("--validation-json", help="Path to ValidationResult JSON file")
    parser.add_argument("--execution-json", help="Path to ExecutionResult JSON file")
    parser.add_argument("--monitoring-json", help="Path to MonitoringResult JSON file")
    parser.add_argument("--demo", action="store_true", help="Run response generation demo on synthetic Passport Seva contracts")
    parser.add_argument("--fallback-only", action="store_true", help="Skip Ollama; use deterministic formatting")
    parser.add_argument("--language", help="Response language preference (e.g. English, Hindi, Tamil)")
    parser.add_argument("--detail-level", choices=["brief", "standard", "detailed"], default="standard")
    parser.add_argument("--json", action="store_true", help="Output full CitizenResponse JSON payload")
    parser.add_argument("--save-json", metavar="PATH", help="Write CitizenResponse JSON to file")
    args = parser.parse_args(argv)

    try:
        request, synthetic = _load_request(args)
    except Exception as exc:
        print(f"Error loading response request: {exc}", file=sys.stderr)
        return 2

    agent = ResponseGenerationAgent(allow_llm=not args.fallback_only)
    try:
        result = agent.generate_citizen_response(request)
    except ResponseGenerationError as exc:
        print(f"Response generation error: {exc}", file=sys.stderr)
        return 1

    print("\n" + result.formatted_markdown)

    if args.json:
        print("\n--- CitizenResponse JSON Payload ---")
        print(result.model_dump_json(indent=2))

    if args.save_json:
        Path(args.save_json).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote CitizenResponse JSON to {args.save_json}")

    return 0


def _load_request(args: argparse.Namespace) -> tuple[ResponseGenerationRequest, bool]:
    if args.request_json:
        payload = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
        req = ResponseGenerationRequest.model_validate(payload)
        if args.language:
            req.response_language = args.language
        return req, False

    if args.intent_json and args.profile_json and args.evidence_json and args.plan_json and args.validation_json:
        intent = IntentResult.model_validate(json.loads(Path(args.intent_json).read_text(encoding="utf-8")))
        profile = ProfileContextResult.model_validate(json.loads(Path(args.profile_json).read_text(encoding="utf-8")))
        evidence = RetrievedEvidenceResult.model_validate(json.loads(Path(args.evidence_json).read_text(encoding="utf-8")))
        plan = WorkflowPlan.model_validate(json.loads(Path(args.plan_json).read_text(encoding="utf-8")))
        val = ValidationResult.model_validate(json.loads(Path(args.validation_json).read_text(encoding="utf-8")))
        exec_res = ExecutionResult.model_validate(json.loads(Path(args.execution_json).read_text(encoding="utf-8"))) if args.execution_json else None
        mon_res = MonitoringResult.model_validate(json.loads(Path(args.monitoring_json).read_text(encoding="utf-8"))) if args.monitoring_json else None

        req = ResponseGenerationRequest(
            response_request_id=str(uuid4()),
            request_id=intent.request_id,
            intent=intent,
            profile_context=profile,
            retrieved_evidence=evidence,
            workflow_plan=plan,
            validation_result=val,
            execution_result=exec_res,
            monitoring_result=mon_res,
            response_language=args.language,
            detail_level=DetailLevel(args.detail_level),
        )
        return req, False

    if args.demo or not any([args.request_json, args.intent_json]):
        print("Using synthetic Passport Seva upstream contracts for response generation demo.")
        req = ResponseGenerationRequest(
            response_request_id="demo-resp-req-001",
            request_id=SYNTHETIC_INTENT.request_id,
            intent=SYNTHETIC_INTENT,
            profile_context=SYNTHETIC_PROFILE,
            retrieved_evidence=SYNTHETIC_EVIDENCE,
            workflow_plan=SYNTHETIC_PLAN,
            validation_result=SYNTHETIC_VALIDATION,
            execution_result=None,
            monitoring_result=SYNTHETIC_MONITORING,
            response_language=args.language,
            detail_level=DetailLevel(args.detail_level),
        )
        return req, True

    print(
        "Provide --request-json, OR (--intent-json, --profile-json, --evidence-json, --plan-json, --validation-json), OR --demo.",
        file=sys.stderr,
    )
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
