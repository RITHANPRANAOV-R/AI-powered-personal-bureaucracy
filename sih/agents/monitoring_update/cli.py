"""CLI and demonstration flow for Monitoring & Update Agent."""

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
from agents.intent_understanding.schema import Complexity, IntentResult, IntentStatus, TaskType
from agents.workflow_planning.schema import (
    EvidenceSupportStatus,
    PlanStep,
    PlanStatus,
    PlanningMode,
    StepStatus,
    StepType,
    WorkflowPlan,
)

from .agent import MonitoringAgentError, MonitoringUpdateAgent
from .schema import (
    MonitoringRequest,
    MonitoringResult,
    UserReportedUpdate,
)
from .storage import MonitoringStore


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
            status=StepStatus.IN_PROGRESS,
            depends_on=["review-official-requirements"],
            required_fact_keys=["full_name", "email"],
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
    execution_authorized=False,
    validated_at="2026-09-23T17:10:00+00:00",
    summary="Validation decision: APPROVE.",
)

SYNTHETIC_EXECUTION = ExecutionResult(
    contract_version="1.0",
    execution_request_id="demo-exec-req-001",
    request_id="demo-passport-register-001",
    plan_id="plan-demo-001",
    plan_version=1,
    validation_request_id="demo-val-req-001",
    execution_status=ExecutionStatus.SUBMISSION_ATTEMPTED,
    step_results=[
        StepExecutionResult(
            step_id="review-official-requirements",
            status=StepExecutionStatus.COMPLETED,
            action_summary="Reviewed official requirements.",
            started_at="2026-09-23T18:00:00+00:00",
            completed_at="2026-09-23T18:00:01+00:00",
        ),
        StepExecutionResult(
            step_id="user-controlled-portal-action",
            status=StepExecutionStatus.COMPLETED,
            action_summary="Prepared registration form and clicked Submit with exact user approval.",
            started_at="2026-09-23T18:00:02+00:00",
            completed_at="2026-09-23T18:00:05+00:00",
        ),
    ],
    field_actions=[
        FieldActionRecord(
            field_label="Passport Seva field (full_name)",
            approval_id="appr-001",
            outcome="filled",
            masked_value="P********r",
        )
    ],
    portal_observations=[
        PortalObservation(
            observation_id="obs-001",
            page_title="Passport Seva User Registration | Official Portal",
            url="https://www.passportindia.gov.in/psp/",
            visible_status="Submitted registration form on official portal",
            observed_at="2026-09-23T18:00:05+00:00",
            source_type="playwright_visible_page",
        )
    ],
    approval_records_used=["exec-appr-001", "exec-appr-002"],
    submission_attempted=True,
    confirmation_observed=False,
    confirmation_reference=None,
    warnings=["Submission was attempted. Portal confirmation is pending manual user verification."],
    completed_at="2026-09-23T18:00:05+00:00",
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Monitoring & Update Agent CLI. Deterministic workflow status tracking and event log."
    )
    parser.add_argument("--request-json", help="Path to MonitoringRequest JSON file")
    parser.add_argument("--intent-json", help="Path to IntentResult JSON file")
    parser.add_argument("--plan-json", help="Path to WorkflowPlan JSON file")
    parser.add_argument("--validation-json", help="Path to ValidationResult JSON file")
    parser.add_argument("--execution-json", help="Path to ExecutionResult JSON file")
    parser.add_argument("--demo", action="store_true", help="Run monitoring update demo on synthetic Passport Seva contracts")
    parser.add_argument("--status", action="store_true", help="Display current workflow monitoring status")
    parser.add_argument(
        "--report-update",
        metavar="STEP_ID=STATUS",
        action="append",
        default=[],
        help="Report a user-entered status update (repeatable), e.g. user-controlled-portal-action=confirmed",
    )
    parser.add_argument("--reminders", action="store_true", help="Display local CLI reminders")
    parser.add_argument("--erase", action="store_true", help="Erase local monitoring state")
    parser.add_argument("--json", action="store_true", help="Output full MonitoringResult JSON payload")
    parser.add_argument("--save-json", metavar="PATH", help="Write MonitoringResult JSON to file")
    args = parser.parse_args(argv)

    store = MonitoringStore()

    if args.erase:
        erased = store.erase()
        print(f"Local monitoring state erased: {erased}")
        return 0

    user_updates = _parse_user_updates(args.report_update)

    try:
        request, synthetic = _load_request(args, store, user_updates)
    except Exception as exc:
        print(f"Error loading monitoring request: {exc}", file=sys.stderr)
        return 2

    agent = MonitoringUpdateAgent()
    try:
        result = agent.update_monitoring_state(request)
    except MonitoringAgentError as exc:
        print(f"Monitoring error: {exc}", file=sys.stderr)
        return 1

    # Save snapshot and append events
    store.save(result)
    store.append_events(result.status_events)

    _display_result(result, synthetic=synthetic, show_reminders=args.reminders)

    if args.json:
        print("\n--- MonitoringResult JSON Payload ---")
        print(result.model_dump_json(indent=2))

    if args.save_json:
        Path(args.save_json).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote MonitoringResult JSON to {args.save_json}")

    return 0


def _load_request(
    args: argparse.Namespace, store: MonitoringStore, user_updates: list[UserReportedUpdate]
) -> tuple[MonitoringRequest, bool]:
    prev_mon = store.load_latest()

    if args.request_json:
        payload = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
        req = MonitoringRequest.model_validate(payload)
        if user_updates:
            req.user_reported_updates.extend(user_updates)
        return req, False

    if args.intent_json and args.plan_json and args.validation_json:
        intent = IntentResult.model_validate(json.loads(Path(args.intent_json).read_text(encoding="utf-8")))
        plan = WorkflowPlan.model_validate(json.loads(Path(args.plan_json).read_text(encoding="utf-8")))
        val = ValidationResult.model_validate(json.loads(Path(args.validation_json).read_text(encoding="utf-8")))
        exec_res = None
        if args.execution_json:
            exec_res = ExecutionResult.model_validate(json.loads(Path(args.execution_json).read_text(encoding="utf-8")))

        req = MonitoringRequest(
            monitoring_request_id=str(uuid4()),
            request_id=intent.request_id,
            intent=intent,
            workflow_plan=plan,
            validation_result=val,
            execution_result=exec_res,
            previous_monitoring_result=prev_mon,
            user_reported_updates=user_updates,
        )
        return req, False

    if args.demo or not any([args.request_json, args.intent_json]):
        print("Using synthetic Passport Seva upstream contracts for monitoring demo.")
        req = MonitoringRequest(
            monitoring_request_id="demo-mon-req-001",
            request_id=SYNTHETIC_INTENT.request_id,
            intent=SYNTHETIC_INTENT,
            workflow_plan=SYNTHETIC_PLAN,
            validation_result=SYNTHETIC_VALIDATION,
            execution_result=SYNTHETIC_EXECUTION,
            previous_monitoring_result=prev_mon,
            user_reported_updates=user_updates,
        )
        return req, True

    print(
        "Provide --request-json, OR (--intent-json, --plan-json, --validation-json), OR --demo.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _parse_user_updates(raw: list[str]) -> list[UserReportedUpdate]:
    updates: list[UserReportedUpdate] = []
    for item in raw:
        if "=" not in item:
            continue
        step_id, status = item.split("=", 1)
        step_id = step_id.strip()
        status = status.strip()
        if step_id and status:
            updates.append(
                UserReportedUpdate(
                    step_id=step_id,
                    reported_status=status,
                    user_notes="Entered via CLI --report-update",
                    reported_at=str(uuid4()),
                )
            )
    return updates


def _display_result(result: MonitoringResult, synthetic: bool = False, show_reminders: bool = False) -> None:
    print("\n=== Monitoring & Update Result ===")
    if synthetic:
        print("Data label: SYNTHETIC upstream contracts")
    print(f"monitoring_request_id: {result.monitoring_request_id}")
    print(f"request_id:            {result.request_id}")
    print(f"plan_id:               {result.plan_id} v{result.plan_version}")
    print(f"monitoring_status:     {result.monitoring_status.value.upper()}")
    print(f"workflow_status:       {result.workflow_status.upper()}")
    if result.portal_observed_status:
        print(f"portal_observed_status:{result.portal_observed_status}")
    if result.user_reported_status:
        print(f"user_reported_status:  {result.user_reported_status} (USER REPORTED)")

    print("\nstep statuses:")
    for step_s in result.step_statuses:
        print(f"  - [{step_s.step_id}] -> status: {step_s.current_status.upper()} (Source: {step_s.last_source_type.value})")

    if result.changes_detected:
        print("\nchanges detected since previous run:")
        for chg in result.changes_detected:
            print(f"  - [{chg.step_id}] {chg.field_name}: '{chg.previous_value}' -> '{chg.current_value}' (Source: {chg.source_type.value})")

    if result.pending_actions:
        print("\npending actions:")
        for act in result.pending_actions:
            print(f"  - [{act.step_id}] {act.action_title} (Assigned: {act.assigned_to}) -> {act.reason}")

    if result.manual_follow_up:
        print("\nmanual follow-up instruction:")
        print(f"  Title: {result.manual_follow_up.title}")
        print(f"  URL:   {result.manual_follow_up.official_url}")
        print(f"  Note:  {result.manual_follow_up.instructions}")

    if result.reminders or show_reminders:
        print("\nlocal CLI reminders:")
        for rem in result.reminders:
            due_tag = "[DUE]" if rem.is_due else ""
            print(f"  - [{rem.step_id}] {due_tag} {rem.message}")

    if result.warnings:
        print("\nwarnings:")
        for w in result.warnings:
            print(f"  - {w}")

    print(f"\nupdated_at: {result.updated_at}")


if __name__ == "__main__":
    raise SystemExit(main())
