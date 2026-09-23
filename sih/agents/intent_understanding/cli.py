"""Terminal demo for the Intent Understanding Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .agent import IntentUnderstandingAgent
from .schema import IntentRequest, IntentResult


PASSPORT_EXAMPLE = (
    "I am a first-time applicant and need to register on Passport Seva "
    "to apply for a new ordinary passport in Tamil Nadu."
)
AMBIGUOUS_EXAMPLE = "I need to update my document."


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Intent Understanding Agent terminal demo. No passwords, OTPs, or payment details are requested."
    )
    parser.add_argument("--goal", help="User goal. If omitted, you will be prompted.")
    parser.add_argument("--language", help="Optional stated language preference.")
    parser.add_argument("--jurisdiction", help="Optional stated location/jurisdiction.")
    parser.add_argument("--user-context", default="", help="Optional authorized profile summary from the caller.")
    parser.add_argument("--document-context", action="append", default=[], help="Optional document snippet. Repeatable.")
    parser.add_argument("--conversation-context", default="", help="Optional prior-turn context.")
    parser.add_argument("--json", action="store_true", help="Print the validated IntentResult JSON to stdout.")
    parser.add_argument(
        "--save-json",
        metavar="PATH",
        help="Write IntentResult JSON to this path. The raw goal is not saved unless you set this.",
    )
    parser.add_argument("--fallback-only", action="store_true", help="Skip Ollama and use the deterministic fallback.")
    parser.add_argument("--no-follow-up", action="store_true", help="Do not prompt for a follow-up answer.")
    parser.add_argument(
        "--with-profile",
        action="store_true",
        help="After intent classification, run the User Context & Profile Agent on the authorized vault.",
    )
    parser.add_argument("--vault-dir", help="Authorized vault directory for --with-profile.")
    parser.add_argument("--profile-path", help="Local profile JSON path for --with-profile.")
    parser.add_argument(
        "--requested-fact",
        action="append",
        default=[],
        dest="requested_facts",
        help="Optional exact fact key required later. Repeatable. Used only with --with-profile.",
    )
    args = parser.parse_args(argv)

    agent = IntentUnderstandingAgent(prefer_ollama=not args.fallback_only)
    request = _build_request(args)
    run = agent.understand_intent_with_meta(request)
    _display(run.result, run.execution_mode, run.fallback_reason, show_json=args.json)
    _maybe_save(run.result, args.save_json)

    latest = run.result
    if not args.no_follow_up and sys.stdin.isatty():
        follow = input("\nFollow-up answer (leave blank to skip): ").strip()
        if follow:
            conversation = _conversation_handoff(run.result, follow)
            follow_request = IntentRequest(
                contract_version=run.result.contract_version,
                request_id=run.result.request_id,
                user_goal=follow,
                language_preference=args.language,
                jurisdiction_hint=args.jurisdiction,
                user_context=args.user_context or "",
                document_context=args.document_context or [],
                conversation_context=conversation,
            )
            follow_run = agent.understand_intent_with_meta(follow_request)
            print("\n--- Follow-up classification ---")
            _display(
                follow_run.result,
                follow_run.execution_mode,
                follow_run.fallback_reason,
                show_json=args.json,
            )
            _maybe_save(follow_run.result, args.save_json)
            latest = follow_run.result

    if args.with_profile:
        from agents.user_context.cli import run_from_intent

        run_from_intent(
            latest,
            vault_dir=args.vault_dir,
            profile_path=args.profile_path,
            requested_facts=args.requested_facts,
            allow_model=not args.fallback_only,
            interview=sys.stdin.isatty() and not args.no_follow_up,
            show_json=args.json,
        )
    return 0


def _build_request(args: argparse.Namespace) -> IntentRequest:
    goal = (args.goal or "").strip()
    language = args.language
    jurisdiction = args.jurisdiction
    user_context = args.user_context or ""
    documents = list(args.document_context or [])
    conversation = args.conversation_context or ""

    if not goal and sys.stdin.isatty():
        print("Intent Understanding Agent")
        print("Do not enter passwords, OTPs, CAPTCHA values, or payment credentials.")
        print(f"Example (clear):     {PASSPORT_EXAMPLE}")
        print(f"Example (ambiguous): {AMBIGUOUS_EXAMPLE}")
        goal = input("\nWhat do you want to get done? ").strip()
        language = language or input("Language preference (optional): ").strip() or None
        jurisdiction = jurisdiction or input("Location/jurisdiction if you stated one (optional): ").strip() or None
        user_context = user_context or input("Caller-supplied profile summary (optional): ").strip()
        extra_docs = input("Document snippets, separated by | (optional): ").strip()
        if extra_docs:
            documents.extend(part.strip() for part in extra_docs.split("|") if part.strip())
        conversation = conversation or input("Prior conversation context (optional): ").strip()

    if not goal:
        print("A user goal is required.", file=sys.stderr)
        raise SystemExit(2)

    return IntentRequest(
        user_goal=goal,
        language_preference=language,
        jurisdiction_hint=jurisdiction,
        user_context=user_context,
        document_context=documents,
        conversation_context=conversation,
    )


def _display(
    result: IntentResult,
    execution_mode: str,
    fallback_reason: Optional[str],
    show_json: bool,
) -> None:
    mode_label = "Ollama local" if execution_mode == "ollama_local" else "deterministic fallback"
    print("\n=== Intent Understanding Result ===")
    print(f"Execution mode: {mode_label}")
    if execution_mode != "ollama_local" and fallback_reason:
        print(f"Fallback reason: {fallback_reason}")
        print("This run did not use an LLM.")
    print(f"request_id:     {result.request_id}")
    print(f"status:         {result.status.value}")
    print(f"confidence:     {result.confidence}")
    print(f"service_name:   {result.service_name}")
    print(f"document_type:  {result.document_type}")
    print(f"task_type:      {result.task_type.value}")
    print(f"jurisdiction:   {result.jurisdiction}")
    print(f"language:       {result.language}")
    print(f"urgency:        {result.urgency}")
    print(f"complexity:     {result.complexity.value}")
    print(f"normalized:     {result.normalized_goal}")
    print("stated facts:")
    if result.stated_facts:
        for fact in result.stated_facts:
            print(f"  - [{fact.source.value}] {fact.text}")
    else:
        print("  (none)")
    print("assumptions:")
    if result.assumptions:
        for item in result.assumptions:
            print(f"  - {item}")
    else:
        print("  (none)")
    print("clarification questions:")
    if result.clarification_questions:
        for item in result.clarification_questions:
            print(f"  - {item}")
    else:
        print("  (none)")

    if show_json:
        print("\n--- IntentResult JSON (handoff to the next agent) ---")
        print(result.model_dump_json(indent=2))


def _maybe_save(result: IntentResult, path: Optional[str]) -> None:
    if not path:
        return
    target = Path(path)
    target.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote IntentResult JSON to {target}")


def _conversation_handoff(previous: IntentResult, follow_up: str) -> str:
    questions = "; ".join(previous.clarification_questions) or "(none)"
    return (
        f"Previous goal: {previous.original_goal}. "
        f"Previous status: {previous.status.value}. "
        f"Questions asked: {questions}. "
        f"User follow-up: {follow_up}."
    )


if __name__ == "__main__":
    raise SystemExit(main())
