"""Terminal demo for official-source Information Retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

from agents.intent_understanding.schema import Complexity, IntentResult, IntentStatus, TaskType
from agents.user_context.schema import ProfileContextResult, ProfileStatus

from .agent import InformationRetrievalAgent
from .schema import InformationRetrievalRequest, RetrievedEvidenceResult

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
    relevant_facts=[],
    missing_requested_facts=[],
    processing_mode="deterministic",
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Information Retrieval Agent. Fetches allowlisted official Passport Seva / MEA pages only. "
            "No login, CAPTCHA, form submission, or user-document evidence."
        )
    )
    parser.add_argument("--intent-json", help="Serialized IntentResult JSON")
    parser.add_argument("--profile-json", help="Serialized ProfileContextResult JSON")
    parser.add_argument("--demo", action="store_true", help="Use synthetic Passport Seva contracts (labeled).")
    parser.add_argument("--json", action="store_true", help="Print RetrievedEvidenceResult JSON")
    parser.add_argument("--save-json", metavar="PATH")
    parser.add_argument("--no-semantic", action="store_true", help="Skip Ollama embeddings")
    parser.add_argument("--no-llm", action="store_true", help="Skip Ollama requirement extraction")
    parser.add_argument("--max-sources", type=int, default=6)
    parser.add_argument(
        "--host",
        action="append",
        dest="hosts",
        default=[],
        help="Override allowlisted host (repeatable). Default is Passport Seva / MEA.",
    )
    args = parser.parse_args(argv)

    intent, profile, synthetic = _load_contracts(args)
    request = InformationRetrievalRequest(
        request_id=str(uuid4()) if not synthetic else "demo-retrieval-001",
        intent=intent,
        profile_context=profile,
        allowed_source_hosts=args.hosts,
        max_sources=args.max_sources,
        use_semantic_search=not args.no_semantic,
        language=intent.language,
    )
    agent = InformationRetrievalAgent(allow_llm=not args.no_llm)
    result = agent.retrieve_information(request)
    _display(result, synthetic=synthetic)
    if args.json:
        print("\n--- RetrievedEvidenceResult JSON (handoff to Workflow Planning) ---")
        print(result.model_dump_json(indent=2))
    if args.save_json:
        Path(args.save_json).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote RetrievedEvidenceResult JSON to {args.save_json}")
    return 0


def _load_contracts(args: argparse.Namespace) -> tuple[IntentResult, ProfileContextResult, bool]:
    if args.intent_json and args.profile_json:
        intent = IntentResult.model_validate(json.loads(Path(args.intent_json).read_text(encoding="utf-8")))
        profile = ProfileContextResult.model_validate(json.loads(Path(args.profile_json).read_text(encoding="utf-8")))
        return intent, profile, False
    if args.demo or (not args.intent_json and not args.profile_json):
        print("Using synthetic IntentResult + ProfileContextResult. Personal vault facts are not queried.")
        return SYNTHETIC_INTENT, SYNTHETIC_PROFILE, True
    print("Provide both --intent-json and --profile-json, or --demo.", file=sys.stderr)
    raise SystemExit(2)


def _display(result: RetrievedEvidenceResult, *, synthetic: bool) -> None:
    print("\n=== Information Retrieval Result ===")
    if synthetic:
        print("Data label: SYNTHETIC intent/profile contracts")
    print(f"processing_mode:  {result.processing_mode.value}")
    if result.processing_mode.value == "deterministic":
        print("Embeddings/LLM were not used for this run (or were unavailable).")
    print(f"retrieval_status: {result.retrieval_status.value}")
    print(f"request_id:       {result.request_id}")
    print(f"service_name:     {result.service_name}")
    print(f"task_type:        {result.task_type.value}")
    print(f"jurisdiction:     {result.jurisdiction}")
    print("search queries:")
    for query in result.search_queries:
        print(f"  - {query.query} ({query.basis})")
    print("sources checked:")
    if result.sources_checked:
        for item in result.sources_checked:
            extra = f" [{item.warning}]" if item.warning else ""
            print(f"  - {item.status.value}: {item.url}{extra}")
    else:
        print("  (none)")
    print(f"evidence records: {len(result.evidence)}")
    for ev in result.evidence[:5]:
        print(f"  - {ev.evidence_id} {ev.source_title} ({ev.source_host})")
        print(f"    {ev.excerpt[:160]}{'…' if len(ev.excerpt) > 160 else ''}")
    print("requirement candidates:")
    if result.requirements_found:
        for req in result.requirements_found:
            print(f"  - {req.requirement_id} cites {', '.join(req.evidence_ids)}: {req.statement[:180]}")
    else:
        print("  (none)")
    if result.unanswered_questions:
        print("unanswered:")
        for item in result.unanswered_questions:
            print(f"  - {item}")
    if result.warnings:
        print("warnings:")
        for item in result.warnings:
            print(f"  - {item}")


if __name__ == "__main__":
    raise SystemExit(main())
