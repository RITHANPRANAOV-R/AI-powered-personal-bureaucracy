"""Terminal demo for Workflow Planning from serialized upstream results."""

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

from .agent import WorkflowPlanningAgent
from .schema import (
    RequestedModelMode,
    WorkflowPlan,
    WorkflowPlanningRequest,
    WorkflowPlanningValidationError,
)

SYNTHETIC_INTENT = IntentResult(
    contract_version="1.0",
    request_id="demo-passport-register-001",
    original_goal=(
        "I am a first-time applicant and need to register on Passport Seva "
        "to apply for a new ordinary passport in Tamil Nadu."
    ),
    normalized_goal=(
        "I am a first-time applicant and need to register on Passport Seva "
        "to apply for a new ordinary passport in Tamil Nadu."
    ),
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
            relevant_to="May be relevant to register for Passport Seva; not a verified government requirement.",
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
            relevant_to="May be relevant to register for Passport Seva; not a verified government requirement.",
            sensitivity=Sensitivity.PERSONAL,
            confirmed_by_user=False,
        ),
    ],
    processing_mode="deterministic",
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
            excerpt=(
                "Register yourself as new user by creating User Id. Provide User Id details "
                "and click Register. E-mail Id is mandatory."
            ),
            content_hash="demo-not-official-hash",
            relevance_score=0.62,
            supports=["req-001"],
        )
    ],
    requirements_found=[
        RequirementCandidate(
            requirement_id="req-001",
            statement="Register yourself as new user by creating User Id. E-mail Id is mandatory.",
            evidence_ids=["ev-001"],
            jurisdiction_scope="unknown",
            source_status=RequirementSourceStatus.OFFICIAL_DATE_UNCLEAR,
            confidence=0.6,
        )
    ],
    unanswered_questions=[],
    warnings=["One or more official sources did not expose a clear publication/update date."],
    processing_mode=ProcessingMode.DETERMINISTIC,
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Workflow Planning Agent. Builds a personalized, ordered plan from "
            "IntentResult + ProfileContextResult + RetrievedEvidenceResult. "
            "Does not search, fill forms, pay, or execute steps."
        )
    )
    parser.add_argument("--intent-json", help="Serialized IntentResult JSON")
    parser.add_argument("--profile-json", help="Serialized ProfileContextResult JSON")
    parser.add_argument("--evidence-json", help="Serialized RetrievedEvidenceResult JSON")
    parser.add_argument("--request-json", help="Serialized WorkflowPlanningRequest JSON")
    parser.add_argument("--prior-plan-json", help="Optional existing WorkflowPlan for re-planning")
    parser.add_argument("--demo", action="store_true", help="Use synthetic Passport Seva upstream contracts (labeled).")
    parser.add_argument("--json", action="store_true", help="Print WorkflowPlan JSON")
    parser.add_argument("--save-json", metavar="PATH", help="Write WorkflowPlan JSON (plan only; no secrets).")
    parser.add_argument("--fallback-only", action="store_true", help="Skip Ollama; labeled deterministic_fallback.")
    parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="User-confirmed planning constraint (repeatable), e.g. language=English",
    )
    args = parser.parse_args(argv)

    try:
        request, synthetic = _load_request(args)
    except WorkflowPlanningValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    agent = WorkflowPlanningAgent(allow_llm=not args.fallback_only)
    result = agent.create_workflow_plan(request)
    _display(result, synthetic=synthetic)
    if args.json:
        print("\n--- WorkflowPlan JSON (handoff to Compliance & Validation) ---")
        print(result.model_dump_json(indent=2))
    if args.save_json:
        Path(args.save_json).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote WorkflowPlan JSON to {args.save_json}")
    return 0


def _load_request(args: argparse.Namespace) -> tuple[WorkflowPlanningRequest, bool]:
    constraints = _parse_constraints(args.constraint)
    prior = None
    if args.prior_plan_json:
        prior = WorkflowPlan.model_validate(json.loads(Path(args.prior_plan_json).read_text(encoding="utf-8")))

    if args.request_json:
        payload = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
        request = WorkflowPlanningRequest.model_validate(payload)
        if args.fallback_only:
            request = request.model_copy(update={"model_mode": RequestedModelMode.DETERMINISTIC_FALLBACK})
        return request, False

    if args.intent_json and args.profile_json and args.evidence_json:
        intent = IntentResult.model_validate(json.loads(Path(args.intent_json).read_text(encoding="utf-8")))
        profile = ProfileContextResult.model_validate(json.loads(Path(args.profile_json).read_text(encoding="utf-8")))
        evidence = RetrievedEvidenceResult.model_validate(
            json.loads(Path(args.evidence_json).read_text(encoding="utf-8"))
        )
        request = WorkflowPlanningRequest(
            planning_request_id=str(uuid4()),
            intent=intent,
            profile_context=profile,
            retrieved_evidence=evidence,
            current_workflow_state=prior,
            user_constraints=constraints,
            model_mode=(
                RequestedModelMode.DETERMINISTIC_FALLBACK if args.fallback_only else RequestedModelMode.AUTO
            ),
        )
        return request, False

    if args.demo or not any([args.intent_json, args.profile_json, args.evidence_json, args.request_json]):
        print("Using synthetic IntentResult + ProfileContextResult + RetrievedEvidenceResult. Not live personal data.")
        request = WorkflowPlanningRequest(
            planning_request_id="demo-planning-001",
            intent=SYNTHETIC_INTENT,
            profile_context=SYNTHETIC_PROFILE,
            retrieved_evidence=SYNTHETIC_EVIDENCE,
            current_workflow_state=prior,
            user_constraints=constraints,
            model_mode=(
                RequestedModelMode.DETERMINISTIC_FALLBACK if args.fallback_only else RequestedModelMode.AUTO
            ),
        )
        return request, True

    print(
        "Provide --intent-json, --profile-json, and --evidence-json together; or --request-json; or --demo.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _parse_constraints(raw: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            out[key] = value
    return out


def _display(result: WorkflowPlan, *, synthetic: bool) -> None:
    print("\n=== Workflow Planning Result ===")
    if synthetic:
        print("Data label: SYNTHETIC upstream contracts")
    print(f"planning_mode:    {result.planning_mode.value}")
    if result.planning_mode.value == "deterministic_fallback":
        print("A local LLM was not used for this plan (or its proposal was rejected).")
    print(f"plan_status:      {result.plan_status.value}")
    print(f"plan_id:          {result.plan_id} v{result.plan_version}")
    print(f"planning_request: {result.planning_request_id}")
    print(f"intent request:   {result.request_id}")
    print(f"service_name:     {result.service_name}")
    print(f"task_type:        {result.task_type.value}")
    print(f"jurisdiction:     {result.jurisdiction}")
    print(f"goal_summary:     {result.goal_summary}")
    print("steps:")
    for step in result.steps:
        deps = f" depends_on={step.depends_on}" if step.depends_on else ""
        print(f"  - [{step.sequence}] {step.step_id} ({step.step_type.value}/{step.status.value}){deps}")
        print(f"    {step.title}")
        if step.evidence_ids:
            print(f"    evidence={step.evidence_ids} ({step.evidence_status.value})")
        if step.blocking_reason:
            print(f"    blocking: {step.blocking_reason}")
    if result.missing_information:
        print("missing information:")
        for item in result.missing_information:
            print(f"  - [{item.source}/{item.status}] {item.question}")
    if result.unresolved_conflicts:
        print("unresolved conflicts:")
        for item in result.unresolved_conflicts:
            print(f"  - {item.topic}: {item.statement}")
    if result.evidence_gaps:
        print("evidence gaps:")
        for item in result.evidence_gaps:
            print(f"  - {item.question}")
    if result.human_approval_points:
        print("human approval points:")
        for item in result.human_approval_points:
            print(f"  - {item.approval_id} -> {item.step_id}")
    if result.warnings:
        print("warnings:")
        for item in result.warnings:
            print(f"  - {item}")
    print(f"created_at:       {result.created_at}")


if __name__ == "__main__":
    raise SystemExit(main())
