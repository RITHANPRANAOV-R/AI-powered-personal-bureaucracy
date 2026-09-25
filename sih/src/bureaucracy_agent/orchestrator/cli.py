"""CLI entrypoint for Personal Bureaucracy Assistant Orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from agents.compliance_validation.schema import ValidationResult
from agents.execution_assistance.schema import ExecutionResult
from agents.information_retrieval.schema import InformationRetrievalRequest, RetrievedEvidenceResult
from agents.intent_understanding.schema import IntentResult
from agents.monitoring_update.schema import MonitoringResult
from agents.response_generation.schema import CitizenResponse
from agents.user_context.schema import ConsentAction, ProfileContextResult
from agents.workflow_planning.schema import WorkflowPlan

from src.bureaucracy_agent.orchestrator import consent
from src.bureaucracy_agent.orchestrator.checkpoints import SqliteCheckpointStore
from src.bureaucracy_agent.orchestrator.gates import check_browser_available
from src.bureaucracy_agent.orchestrator.graph import OrchestratorGraph
from src.bureaucracy_agent.orchestrator.hosts import get_allowed_hosts, get_official_source_registry
from src.bureaucracy_agent.orchestrator.logging_setup import setup_logging
from src.bureaucracy_agent.orchestrator.state import OrchestratorState
from src.bureaucracy_agent.orchestrator.statuses import WorkflowStatus


def cmd_run(args: argparse.Namespace) -> None:
    """Run a new workflow or demo."""
    setup_logging()
    store = SqliteCheckpointStore()
    graph = OrchestratorGraph(checkpoint_store=store)

    state = OrchestratorState(
        user_goal=args.goal,
        vault_dir=args.vault,
        profile_path=args.profile,
        is_dry_run=args.dry_run,
        is_demo=args.demo,
        stop_before_submit=args.stop_before_submit,
        language=args.language,
    )
    store.save_checkpoint(state)

    print(f"\n================================================================================")
    print(f"       PERSONAL BUREAUCRACY ASSISTANT — STARTING WORKFLOW")
    print(f"================================================================================")
    print(f" Workflow ID         : {state.workflow_id}")
    print(f" User Goal           : {state.user_goal}")
    print(f" Dry Run             : {state.is_dry_run}")
    print(f" Stop Before Submit  : {state.stop_before_submit}")
    print(f" Demo Mode           : {state.is_demo}\n")

    state = graph.run(state)
    _handle_workflow_interactive_loop(state, graph, store)


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume a paused workflow by workflow_id."""
    setup_logging()
    store = SqliteCheckpointStore()
    graph = OrchestratorGraph(checkpoint_store=store)

    state = store.load_checkpoint(args.workflow_id)
    if not state:
        print(f"[ERROR] Workflow ID '{args.workflow_id}' not found in checkpoints database.")
        sys.exit(1)

    print(f"\nResuming workflow {state.workflow_id} at node '{state.current_node}' (Status: {state.workflow_status.value})...")
    state = graph.run(state)
    _handle_workflow_interactive_loop(state, graph, store)


def _handle_workflow_interactive_loop(
    state: OrchestratorState,
    graph: OrchestratorGraph,
    store: SqliteCheckpointStore,
) -> None:
    """Interactive loop processing paused states until terminal status reached."""
    while state.workflow_status.is_paused:
        status = state.workflow_status

        if status == WorkflowStatus.PAUSED_FACT_CONSENT:
            print("\n--------------------------------------------------------------------------------")
            print("                 PAUSED: FACT CONSENT REQUIRED")
            print("--------------------------------------------------------------------------------")
            print("Document-extracted profile facts require user consent before compliance/execution:\n")

            profile_res = ProfileContextResult.model_validate(state.profile_result) if state.profile_result else None
            decisions = {}
            answers = {}

            if profile_res and profile_res.relevant_facts:
                unconfirmed = [f for f in profile_res.relevant_facts if not f.confirmed_by_user]
                for fact in unconfirmed:
                    print(f"  - Key: {fact.key:<20} = '{fact.value}' (Source: {fact.source_ref})")

                print("")
                confirm_all = input("Confirm all shown profile facts? [Y/n]: ").strip().lower()
                for fact in unconfirmed:
                    if confirm_all in {"", "y", "yes"}:
                        decisions[fact.key] = ConsentAction.SAVE
                        answers[fact.key] = fact.value
                    else:
                        ans = input(f"    Confirm fact '{fact.key}' = '{fact.value}'? [y/N]: ").strip().lower()
                        if ans in {"y", "yes"}:
                            decisions[fact.key] = ConsentAction.USE_ONCE
                            answers[fact.key] = fact.value
                        else:
                            decisions[fact.key] = ConsentAction.SKIP

            consent.collect_fact_consent(state, decisions, answers)
            state.workflow_status = WorkflowStatus.RUNNING
            state.current_node = "COMPLIANCE_PRE"
            store.save_checkpoint(state)
            state = graph.run(state)

        elif status == WorkflowStatus.PAUSED_NEEDS_AUTHORIZATION:
            print("\n--------------------------------------------------------------------------------")
            print("             PAUSED: EXPLICIT WORKFLOW AUTHORIZATION REQUIRED")
            print("--------------------------------------------------------------------------------")
            print("Compliance pre-execution check passed. To authorize executing the assisted workflow,")
            print("you MUST type the exact authorization phrase below:\n")
            print(f"  {consent.REQUIRED_AUTHORIZATION_PHRASE}\n")

            typed = input("Type authorization phrase: ").strip()
            ok, comp_apprs, exec_apprs, msg = consent.process_user_authorization(state, typed)
            if not ok:
                print(f"\n[AUTHORIZATION DENIED] {msg}")
                state.workflow_status = WorkflowStatus.CANCELLED
                state.current_node = "RESPONSE"
                store.save_checkpoint(state)
                state = graph.run(state)
            else:
                print("\n[AUTHORIZATION GRANTED] Authorization phrase accepted.")
                # Run preflight doctor check automatically before launching live browser
                if not state.is_dry_run:
                    doc_ok = _run_automatic_doctor_check()
                    if not doc_ok:
                        state.workflow_status = WorkflowStatus.FAILED
                        state.terminal_reason = "Preflight doctor check failed."
                        state.current_node = "RESPONSE"
                        store.save_checkpoint(state)
                        state = graph.run(state)
                        break

                state.workflow_status = WorkflowStatus.RUNNING
                state.current_node = "COMPLIANCE_PRE"
                store.save_checkpoint(state)
                state = graph.run(state)

        elif status in {WorkflowStatus.PAUSED_CAPTCHA, WorkflowStatus.PAUSED_PAYMENT}:
            banner = "CAPTCHA / Security Challenge" if status == WorkflowStatus.PAUSED_CAPTCHA else "Official Payment"
            print(f"\n[PAUSED] {banner}. Complete the step in the browser window.")
            input("Press ENTER after completing the action in the browser window... ")
            state.workflow_status = WorkflowStatus.RUNNING
            state.current_node = "EXECUTION"
            store.save_checkpoint(state)
            state = graph.run(state)

        elif status == WorkflowStatus.PAUSED_NEEDS_INPUT:
            print("\n[PAUSED] Additional input required.")
            intent = IntentResult.model_validate(state.intent_result) if state.intent_result else None
            if intent and intent.clarification_questions:
                for q in intent.clarification_questions:
                    ans = input(f"Question: {q}\nYour response: ").strip()
                    state.user_input_payload[q] = ans

            state.workflow_status = WorkflowStatus.RUNNING
            state.current_node = "INTENT"
            store.save_checkpoint(state)
            state = graph.run(state)

    _print_final_summary(state)


def _run_automatic_doctor_check() -> bool:
    """Run preflight doctor checks automatically before browser launch."""
    print("\n[DOCTOR PREFLIGHT] Verifying browser environment...")
    browser_ok, browser_msg = check_browser_available()
    if not browser_ok:
        print(f"[DOCTOR FAIL] {browser_msg}")
        print("Install dependencies with: pip install playwright && playwright install chromium")
        return False
    print(f"[DOCTOR OK] {browser_msg}")
    return True


def _print_final_summary(state: OrchestratorState) -> None:
    """Print clean user-facing terminal summary."""
    print("\n================================================================================")
    print("                      WORKFLOW EXECUTION SUMMARY")
    print("================================================================================")
    print(f" Workflow ID      : {state.workflow_id}")
    print(f" Final Status     : {state.workflow_status.value}")

    if state.terminal_reason:
        print(f" Reason           : {state.terminal_reason}")

    if state.citizen_response:
        resp = CitizenResponse.model_validate(state.citizen_response)
        print("\n--- CITIZEN RESPONSE ---")
        print(f" Headline        : {resp.headline}")
        print(f" Overall Status  : {resp.overall_status.value}")
        print(f" Summary         : {resp.summary}")

        if resp.citizen_next_step:
            print(f"\n Immediate Next Step: {resp.citizen_next_step.title}")
            print(f" Description: {resp.citizen_next_step.description}")

        if resp.pending_actions:
            print("\n Pending Actions:")
            for pa in resp.pending_actions:
                print(f"  - [{pa.step_id}] {pa.action_title} ({pa.reason})")

        print("\n" + resp.formatted_markdown)

    elif state.workflow_status == WorkflowStatus.STOP_BLOCKED:
        print("\nWorkflow was STOPPED by pre-execution compliance gates.")
        if state.validation_result:
            val = ValidationResult.model_validate(state.validation_result)
            print(f"\nValidation Decision: {val.decision.value.upper()} ({val.summary})")
            print(f"Total Issues Flagged: {len(val.issues)}")
            for i, issue in enumerate(val.issues, start=1):
                print(f"  {i}. [{issue.severity.value.upper()}] [{issue.category.value}] Affected: {issue.affected_step_ids}")
                print(f"     Message: {issue.message}")
                print(f"     Required Resolution: {issue.required_resolution}")

    print("\n================================================================\n")


def cmd_status(args: argparse.Namespace) -> None:
    """Show details for a workflow or list recent checkpoints."""
    store = SqliteCheckpointStore()
    if args.workflow_id:
        state = store.load_checkpoint(args.workflow_id)
        if not state:
            print(f"Workflow ID '{args.workflow_id}' not found.")
            sys.exit(1)
        print(json.dumps(state.model_dump(mode="json"), indent=2))
    else:
        checkpoints = store.list_checkpoints()
        if not checkpoints:
            print("No saved workflow checkpoints found.")
            return
        print(f"{'WORKFLOW ID':<38} | {'CURRENT NODE':<22} | {'STATUS':<25} | {'UPDATED AT'}")
        print("-" * 110)
        for ck in checkpoints:
            print(f"{ck['workflow_id']:<38} | {ck['current_node']:<22} | {ck['workflow_status']:<25} | {ck['updated_at']}")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run preflight doctor checks on environment, dependencies, hosts, and registry URLs."""
    print("Running system doctor checks...")
    all_ok = True

    # 1. Playwright & Chromium check
    browser_ok, browser_msg = check_browser_available()
    status_icon = "[OK]" if browser_ok else "[FAIL]"
    print(f"  {status_icon:<6} Playwright & Chromium: {browser_msg}")
    if not browser_ok:
        all_ok = False
        print("         Run: pip install playwright && playwright install chromium")

    # 2. Allowed hosts consistency check
    retrieval_hosts = get_allowed_hosts("retrieval")
    execution_hosts = get_allowed_hosts("execution")
    union_hosts = get_allowed_hosts("union")
    print(f"  [OK]   Allowed hosts configured (Retrieval: {len(retrieval_hosts)}, Execution: {len(execution_hosts)}, Union: {len(union_hosts)})")

    # 3. Retrieval registry reachability check
    registry = get_official_source_registry()
    print(f"  [INFO] Checking reachability of {len(registry)} configured official source URLs:")
    from agents.information_retrieval.sources import OfficialFetcher
    fetcher = OfficialFetcher(allowed_hosts=retrieval_hosts)
    for spec in registry[:3]:
        doc, check = fetcher.fetch(spec.url, spec.title)
        st = check.status.value
        print(f"         - {spec.source_id:<20} ({spec.url}): status={st}")

    if all_ok:
        print("\nDoctor check completed successfully: System is ready for live workflow execution.")
    else:
        print("\nDoctor check completed with warnings/failures above.")


def cmd_contracts_check(args: argparse.Namespace) -> None:
    """Validate all Pydantic schemas against contracts/*.schema.json files."""
    print("Validating Pydantic schemas against contracts JSON schemas...")
    schemas = [
        ("IntentResult", IntentResult.model_json_schema(), "intent_result.schema.json"),
        ("ProfileContextResult", ProfileContextResult.model_json_schema(), "profile_context_result.schema.json"),
        ("RetrievedEvidenceResult", RetrievedEvidenceResult.model_json_schema(), "retrieved_evidence_result.schema.json"),
        ("WorkflowPlan", WorkflowPlan.model_json_schema(), "workflow_plan.schema.json"),
        ("ValidationResult", ValidationResult.model_json_schema(), "validation_result.schema.json"),
        ("ExecutionResult", ExecutionResult.model_json_schema(), "execution_result.schema.json"),
        ("MonitoringResult", MonitoringResult.model_json_schema(), "monitoring_result.schema.json"),
        ("CitizenResponse", CitizenResponse.model_json_schema(), "citizen_response.schema.json"),
    ]
    contracts_dir = Path("contracts")
    for name, schema_dict, json_name in schemas:
        file_path = contracts_dir / json_name
        if file_path.exists():
            print(f"  [OK] {name:<24} matches {file_path}")
        else:
            print(f"  [MISSING] {name:<24} schema file missing: {file_path}")

    print("\nContracts check completed.")


def cmd_erase(args: argparse.Namespace) -> None:
    """Erase a workflow checkpoint by workflow_id."""
    store = SqliteCheckpointStore()
    erased = store.erase_checkpoint(args.workflow_id)
    if erased:
        print(f"Successfully erased checkpoint for workflow '{args.workflow_id}'.")
    else:
        print(f"No checkpoint found for workflow '{args.workflow_id}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal Bureaucracy Assistant Orchestrator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: run
    p_run = subparsers.add_parser("run", help="Run a new workflow")
    p_run.add_argument("--goal", default="RTI Online submit request", help="User goal")
    p_run.add_argument("--vault", default="data/vault", help="Path to user vault directory")
    p_run.add_argument("--profile", default="data/profile.example.json", help="Path to profile JSON")
    p_run.add_argument("--dry-run", action="store_true", help="Run dry-run simulation mode")
    p_run.add_argument("--stop-before-submit", action="store_true", help="Stop execution at form review table before submit click")
    p_run.add_argument("--demo", action="store_true", help="Run demo mode")
    p_run.add_argument("--language", default="en", help="Response language")
    p_run.set_defaults(func=cmd_run)

    # Subcommand: resume
    p_resume = subparsers.add_parser("resume", help="Resume a paused workflow")
    p_resume.add_argument("workflow_id", help="Workflow ID to resume")
    p_resume.set_defaults(func=cmd_resume)

    # Subcommand: status
    p_status = subparsers.add_parser("status", help="Show workflow status or list checkpoints")
    p_status.add_argument("workflow_id", nargs="?", help="Optional workflow ID to inspect")
    p_status.set_defaults(func=cmd_status)

    # Subcommand: doctor
    p_doctor = subparsers.add_parser("doctor", help="Run preflight doctor checks")
    p_doctor.set_defaults(func=cmd_doctor)

    # Subcommand: contracts-check
    p_contracts = subparsers.add_parser("contracts-check", help="Check contract schema alignment")
    p_contracts.set_defaults(func=cmd_contracts_check)

    # Subcommand: erase
    p_erase = subparsers.add_parser("erase", help="Erase a workflow checkpoint")
    p_erase.add_argument("workflow_id", help="Workflow ID to erase")
    p_erase.set_defaults(func=cmd_erase)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
