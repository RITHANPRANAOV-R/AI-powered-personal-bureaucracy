"""Terminal demo and profile management for the User Context & Profile Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from agents.intent_understanding.schema import Complexity, IntentResult, IntentStatus, TaskType

from .agent import UserContextAgent, mask_display_value
from .config import EXAMPLE_PROFILE_PATH, PACKAGE_ROOT, load_profile_config
from .schema import ConsentAction, ProfileContextRequest, ProfileContextResult
from .storage import ProfileStore, is_secret_key

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
    entities=[],
    stated_facts=[],
    language="English",
    complexity=Complexity.MEDIUM,
    confidence=0.74,
    status=IntentStatus.READY,
)


def main(argv: Optional[list[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or raw[0] not in {"run", "profile"}:
        raw = ["run", *raw]
    parser = argparse.ArgumentParser(
        description=(
            "User Context & Profile Agent. Reads only the authorized vault and local profile. "
            "Never enter passwords, OTPs, CAPTCHA values, recovery codes, or payment credentials."
        )
    )
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Scan vault/profile against an IntentResult (default).")
    _add_run_args(run_parser)

    profile_parser = sub.add_parser("profile", help="Review, correct, delete, or erase local profile facts.")
    profile_sub = profile_parser.add_subparsers(dest="profile_command", required=True)
    list_p = profile_sub.add_parser("list", help="List stored confirmed facts (masked).")
    list_p.add_argument("--profile-path")
    del_p = profile_sub.add_parser("delete", help="Delete one stored fact key.")
    del_p.add_argument("--key", required=True)
    del_p.add_argument("--profile-path")
    erase_p = profile_sub.add_parser("erase", help="Delete the local profile JSON file.")
    erase_p.add_argument("--profile-path")
    erase_p.add_argument("--yes", action="store_true")

    args = parser.parse_args(raw)
    if args.command == "profile":
        return _profile_command(args)
    return _run_command(args)


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--intent-json", help="Path to a serialized IntentResult JSON file.")
    parser.add_argument("--demo", action="store_true", help="Use the synthetic Passport Seva IntentResult and sample vault.")
    parser.add_argument("--vault-dir")
    parser.add_argument("--profile-path")
    parser.add_argument("--requested-fact", action="append", default=[], dest="requested_facts")
    parser.add_argument("--language-pref", help="Optional consented language preference.")
    parser.add_argument("--region-pref", help="Optional consented region preference.")
    parser.add_argument("--no-model", action="store_true", help="Deterministic labeled extraction only.")
    parser.add_argument("--no-interview", action="store_true", help="Do not ask questions or persist facts.")
    parser.add_argument("--json", action="store_true", help="Print ProfileContextResult JSON.")
    parser.add_argument("--save-json", metavar="PATH", help="Write ProfileContextResult JSON to this path.")


def run_from_intent(
    intent: IntentResult,
    *,
    vault_dir: Optional[str] = None,
    profile_path: Optional[str] = None,
    requested_facts: Optional[list[str]] = None,
    allow_model: bool = True,
    interview: bool = True,
    show_json: bool = False,
    save_json: Optional[str] = None,
    language_pref: Optional[str] = None,
    region_pref: Optional[str] = None,
    demo: bool = False,
) -> ProfileContextResult:
    config = load_profile_config()
    vault = Path(vault_dir) if vault_dir else config.vault_dir
    persist_profile = Path(profile_path) if profile_path else config.profile_path
    load_profile = persist_profile
    if demo:
        if not vault_dir:
            vault = PACKAGE_ROOT / "data" / "vault"
        load_profile = EXAMPLE_PROFILE_PATH if EXAMPLE_PROFILE_PATH.exists() else persist_profile

    prefs = {}
    if language_pref:
        prefs["language_preference"] = language_pref
    if region_pref:
        prefs["state"] = region_pref

    request = ProfileContextRequest(
        request_id=intent.request_id,
        intent=intent,
        vault_dir=str(vault),
        profile_path=str(load_profile),
        requested_fact_keys=requested_facts or [],
        user_preferences=prefs,
        allow_model_extraction=allow_model,
        save_confirmed_facts=False,
    )
    agent = UserContextAgent(config)
    result = agent.build_user_context(request)
    _display(result)

    if interview and sys.stdin.isatty() and (
        result.missing_requested_facts or result.conflicts or result.questions_for_user
    ):
        decisions, answers = _interview(result)
        persist_path = str(persist_profile)
        follow_request = request.model_copy(
            update={
                "save_confirmed_facts": any(action == ConsentAction.SAVE for action in decisions.values()),
                "profile_path": persist_path,
            }
        )
        result = agent.apply_consent(follow_request, result, decisions, answers)
        print("\n--- After consent ---")
        _display(result)

    if show_json:
        print("\n--- ProfileContextResult JSON (handoff to Information Retrieval) ---")
        print(result.model_dump_json(indent=2))
    if save_json:
        Path(save_json).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote ProfileContextResult JSON to {save_json}")
    return result


def _run_command(args: argparse.Namespace) -> int:
    intent = _load_intent(args)
    run_from_intent(
        intent,
        vault_dir=args.vault_dir,
        profile_path=args.profile_path,
        requested_facts=args.requested_facts,
        allow_model=not args.no_model,
        interview=not args.no_interview,
        show_json=args.json,
        save_json=args.save_json,
        language_pref=args.language_pref,
        region_pref=args.region_pref,
        demo=args.demo,
    )
    return 0


def _load_intent(args: argparse.Namespace) -> IntentResult:
    if args.intent_json:
        payload = json.loads(Path(args.intent_json).read_text(encoding="utf-8"))
        return IntentResult.model_validate(payload)
    if args.demo or sys.stdin.isatty():
        if not args.intent_json:
            print("Using synthetic Passport Seva IntentResult for a focused demo.")
            return SYNTHETIC_INTENT
    print("Provide --intent-json or --demo.", file=sys.stderr)
    raise SystemExit(2)


def _display(result: ProfileContextResult) -> None:
    print("\n=== User Context & Profile Result ===")
    print(f"processing_mode: {result.processing_mode.value}")
    if result.processing_mode.value == "deterministic":
        print("This run did not use an LLM for fact extraction." if not any("Model extraction" in w for w in result.warnings) else "Model extraction was skipped; labeled/deterministic facts only.")
    print(f"request_id:      {result.request_id}")
    print(f"profile_status:  {result.profile_status.value}")
    print(f"service_name:    {result.service_name}")
    print(f"task_type:       {result.task_type.value}")
    print(f"jurisdiction:    {result.jurisdiction}")
    print(f"profile_updated: {result.profile_updated}")
    print("scanned files:")
    if result.scanned_files:
        for item in result.scanned_files:
            extra = f" ({item.warning})" if item.warning else ""
            print(f"  - {item.relative_path}: {item.status.value}{extra}")
    else:
        print("  (none)")
    print("relevant facts (masked in the terminal):")
    if result.relevant_facts:
        for fact in result.relevant_facts:
            confirmed = "confirmed" if fact.confirmed_by_user else fact.status.value
            print(
                f"  - {fact.key}={mask_display_value(fact)} "
                f"[{confirmed}; {fact.source_type.value}:{fact.source_ref}; {fact.sensitivity.value}]"
            )
    else:
        print("  (none)")
    if result.conflicts:
        print("conflicts:")
        for conflict in result.conflicts:
            print(f"  - {conflict.key}: {conflict.note} sources={conflict.source_refs}")
    if result.missing_requested_facts:
        print(f"missing requested facts: {', '.join(result.missing_requested_facts)}")
    if result.questions_for_user:
        print("questions:")
        for question in result.questions_for_user:
            print(f"  - {question}")
    if result.warnings:
        print("warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    if result.consent_updates:
        print("consent updates (keys only):")
        for item in result.consent_updates:
            print(f"  - {item.key}: {item.action.value} persisted={item.persisted}")


def _interview(result: ProfileContextResult) -> tuple[dict[str, ConsentAction], dict[str, str]]:
    print("\nDo not enter passwords, OTPs, CAPTCHA values, recovery codes, or payment details.")
    print("Missing/conflicting items are from requested keys or vault/profile disagreement.")
    print("They are not official Passport Seva requirements unless a later retrieval agent says so.")
    decisions: dict[str, ConsentAction] = {}
    answers: dict[str, str] = {}

    for key in result.missing_requested_facts:
        raw = input(f"\nEnter {key.replace('_', ' ')} (blank to skip): ").strip()
        if not raw:
            decisions[key] = ConsentAction.SKIP
            continue
        if is_secret_key(key):
            print("That key looks like a secret and will not be stored.")
            decisions[key] = ConsentAction.SKIP
            continue
        action = _ask_consent(key)
        decisions[key] = action
        if action != ConsentAction.SKIP:
            answers[key] = raw

    conflict_keys = {item.key for item in result.conflicts}
    for conflict in result.conflicts:
        print(f"\nConflict on {conflict.key}: {conflict.competing_values}")
        raw = input(f"Correct value for {conflict.key} (blank to skip): ").strip()
        if not raw:
            decisions[conflict.key] = ConsentAction.SKIP
            continue
        action = _ask_consent(conflict.key)
        decisions[conflict.key] = action
        if action != ConsentAction.SKIP:
            answers[conflict.key] = raw

    for fact in result.relevant_facts:
        if fact.confirmed_by_user:
            continue
        if fact.key in result.missing_requested_facts or fact.key in conflict_keys:
            if fact.key in decisions:
                continue
            print(f"\nCandidate {fact.key}={mask_display_value(fact)} from {fact.source_ref}")
            action = _ask_consent(fact.key)
            decisions[fact.key] = action
    return decisions, answers


def _ask_consent(key: str) -> ConsentAction:
    raw = input(
        f"Save '{key}' to the local profile? [save / use once / skip]: "
    ).strip().lower()
    if raw in {"save", "s"}:
        return ConsentAction.SAVE
    if raw in {"skip", "n", "no"}:
        return ConsentAction.SKIP
    return ConsentAction.USE_ONCE


def _profile_command(args: argparse.Namespace) -> int:
    config = load_profile_config()
    path = Path(args.profile_path) if getattr(args, "profile_path", None) else config.profile_path
    store = ProfileStore(path)
    if args.profile_command == "list":
        facts = store.load()
        if not facts:
            print(f"No confirmed facts in {path}")
            return 0
        print(f"Confirmed facts in {path} (values masked):")
        for fact in facts:
            print(f"  - {fact.key}={mask_display_value(fact)} updated={fact.extracted_at}")
        return 0
    if args.profile_command == "delete":
        if is_secret_key(args.key):
            print("Refusing secret-like key.")
            return 2
        if store.delete_key(args.key):
            print(f"Deleted {args.key}")
            return 0
        print(f"No fact named {args.key}")
        return 1
    if args.profile_command == "erase":
        if not args.yes:
            confirm = input(f"Erase local profile at {path}? Type YES: ").strip()
            if confirm != "YES":
                print("Cancelled.")
                return 1
        if store.erase():
            print(f"Erased {path}")
        else:
            print("No profile file to erase.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
