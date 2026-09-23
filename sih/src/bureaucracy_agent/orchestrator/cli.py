"""Comprehensive Orchestrator CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from src.bureaucracy_agent.orchestrator.state import OrchestratorState, OneRunAuthorization
from src.bureaucracy_agent.orchestrator.graph import OrchestratorGraph
from src.bureaucracy_agent.orchestrator.checkpoints import SqliteCheckpointStore
from src.bureaucracy_agent.orchestrator.approvals import validate_upfront_phrase, UPFRONT_AUTHORIZATION_PHRASE
from agents.audit import check_all_contracts


def cmd_run(args: argparse.Namespace) -> None:
    """Run an end-to-end multi-agent workflow."""
    print(f"\n--- Starting Bureaucracy Assistant Orchestrator ---")
    print(f"Goal: {args.goal}")
    print(f"Language: {args.language}")
    print(f"Mode: {'Demo/Dry-Run' if args.demo or args.dry_run else 'Live Execution'}")

    state = OrchestratorState(
        user_goal=args.goal,
        language=args.language,
        is_demo=args.demo or args.dry_run,
        is_dry_run=args.dry_run or args.demo,
    )

    # Check upfront authorization
    auth_phrase = args.auth or ""
    if not auth_phrase and not (args.demo or args.dry_run):
        print(f"\n[Authorization Required] Enter upfront authorization phrase to proceed:")
        print(f"Required Phrase: '{UPFRONT_AUTHORIZATION_PHRASE}'")
        try:
            auth_phrase = input("Authorization Phrase > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nWorkflow cancelled by user.")
            sys.exit(0)

    if validate_upfront_phrase(auth_phrase) or args.demo or args.dry_run:
        state.one_run_authorization = OneRunAuthorization(
            phrase=auth_phrase if auth_phrase else UPFRONT_AUTHORIZATION_PHRASE,
            scope="PASSPORT SEVA REGISTRATION AND SUBMISSION",
            authorized=True,
        )
        print("[+] Upfront authorization verified.")
    else:
        print("[-] Invalid authorization phrase. Upfront authorization NOT granted.")

    graph = OrchestratorGraph()
    final_state = graph.run(state)

    print(f"\n--- Execution Completed ---")
    print(f"Workflow ID: {final_state.workflow_id}")
    print(f"Status: {final_state.workflow_status}")
    print(f"Current Node: {final_state.current_node}")

    if final_state.citizen_response:
        print("\n=== Citizen Response Summary ===")
        print(final_state.citizen_response.get("summary", "No summary available."))
        print("\nActionable Steps:")
        for step in final_state.citizen_response.get("actionable_steps", []):
            print(f"  - {step}")


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume a paused workflow checkpoint by workflow_id."""
    store = SqliteCheckpointStore()
    state = store.load_checkpoint(args.workflow_id)
    if not state:
        print(f"[-] No saved checkpoint found for workflow_id: {args.workflow_id}")
        sys.exit(1)

    print(f"\n--- Resuming Workflow {state.workflow_id} ---")
    print(f"Current Node: {state.current_node}")
    print(f"Status: {state.workflow_status}")

    graph = OrchestratorGraph(checkpoint_store=store)
    final_state = graph.run(state)
    print(f"\nUpdated Status: {final_state.workflow_status}")


def cmd_status(args: argparse.Namespace) -> None:
    """Check workflow status or list active checkpoints."""
    store = SqliteCheckpointStore()
    if args.workflow_id:
        state = store.load_checkpoint(args.workflow_id)
        if not state:
            print(f"[-] No checkpoint found for workflow_id: {args.workflow_id}")
            sys.exit(1)
        print(json.dumps(state.model_dump(mode="json"), indent=2))
    else:
        checkpoints = store.list_checkpoints()
        print(f"\n--- Active Workflow Checkpoints ({len(checkpoints)}) ---")
        for cp in checkpoints:
            print(f"ID: {cp['workflow_id']} | Node: {cp['current_node']} | Status: {cp['workflow_status']} | Updated: {cp['updated_at']}")


def cmd_contracts_check(args: argparse.Namespace) -> None:
    """Audit all 8 specialist agent contracts against stored JSON schemas."""
    print("\n--- Running Static Contract & Schema Audit ---")
    audit_res = check_all_contracts()
    print(json.dumps(audit_res, indent=2))
    if audit_res.get("status") == "PASS":
        print(f"\n[+] CONTRACT AUDIT PASSED: All {audit_res.get('total_contracts')} agent schemas match version '1.0'.")
        sys.exit(0)
    else:
        print(f"\n[-] CONTRACT AUDIT FAILED: Contract schema mismatches detected.")
        sys.exit(1)


def cmd_erase_data(args: argparse.Namespace) -> None:
    """Erase local orchestrator checkpoints and temporary runtime data."""
    store = SqliteCheckpointStore()
    count = store.erase_checkpoints()
    print(f"[+] Erased {count} workflow checkpoints from SQLite store.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="orchestrator", description="Personal Bureaucracy Assistant Orchestrator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_p = subparsers.add_parser("run", help="Run end-to-end multi-agent workflow")
    run_p.add_argument("--goal", type=str, default="Passport Seva online registration", help="User prompt or goal")
    run_p.add_argument("--auth", type=str, default="", help="Upfront authorization phrase")
    run_p.add_argument("--demo", action="store_true", help="Run in demo mode (dry run)")
    run_p.add_argument("--dry-run", action="store_true", help="Run in dry run mode")
    run_p.add_argument("--language", type=str, default="en", help="User preferred language")

    # resume command
    resume_p = subparsers.add_parser("resume", help="Resume a paused workflow")
    resume_p.add_argument("--workflow-id", type=str, required=True, help="Workflow ID to resume")
    resume_p.add_argument("--auth", type=str, default="", help="Authorization phrase if required")

    # status command
    status_p = subparsers.add_parser("status", help="Show workflow status")
    status_p.add_argument("--workflow-id", type=str, default="", help="Specific workflow ID")

    # contracts-check command
    subparsers.add_parser("contracts-check", help="Audit all 8 specialist agent Pydantic contracts and schemas")

    # erase command
    subparsers.add_parser("erase-local-agent-data", help="Erase local checkpoints and runtime state")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "resume":
        cmd_resume(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "contracts-check":
        cmd_contracts_check(args)
    elif args.command == "erase-local-agent-data":
        cmd_erase_data(args)


if __name__ == "__main__":
    main()
