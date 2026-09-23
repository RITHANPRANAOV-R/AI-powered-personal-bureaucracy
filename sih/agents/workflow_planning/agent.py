"""Workflow Planning Agent: propose a plan, then validate it in Python.

This agent does not search, retrieve, update a profile, fill forms, pay,
book appointments, or execute other agents. A returned WorkflowPlan describes
work; it is not authorization to act.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from agents.information_retrieval.schema import RequirementCandidate, RequirementSourceStatus
from agents.intent_understanding.schema import IntentResult, IntentStatus
from agents.user_context.schema import FactStatus, ProfileContextResult

from .config import PlanningConfig, load_planning_config
from .llm import PlanningModelUnavailable, PlanningOllamaClient, extract_json_object
from .schema import (
    CONTRACT_VERSION,
    EvidenceGap,
    EvidenceSupportStatus,
    MissingInformationItem,
    PlanStep,
    PlanStatus,
    PlanningMode,
    RequestedModelMode,
    StepStatus,
    StepType,
    UnresolvedConflict,
    WorkflowPlan,
    WorkflowPlanningRequest,
    WorkflowPlanningValidationError,
    utc_now,
)
from .validator import (
    collect_contract_issues,
    confirmed_facts,
    dag_errors,
    document_refs_for_keys,
    evidence_status_for,
    fact_keys_mentioned,
    implied_fact_keys,
    looks_consequential,
    sanitize_plan,
    unconfirmed_facts,
    valid_requirements,
)


class WorkflowPlanningAgent:
    def __init__(
        self,
        config: Optional[PlanningConfig] = None,
        *,
        allow_llm: bool = True,
    ) -> None:
        self.config = config or load_planning_config()
        self.allow_llm = allow_llm
        self.ollama = PlanningOllamaClient(self.config)

    def create_workflow_plan(self, request: WorkflowPlanningRequest) -> WorkflowPlan:
        """
        Public callable (synchronous; Ollama is called over HTTP with httpx).

        Signature:
            def create_workflow_plan(request: WorkflowPlanningRequest) -> WorkflowPlan
        """
        try:
            request = WorkflowPlanningRequest.model_validate(request)
        except ValidationError as exc:
            raise WorkflowPlanningValidationError(str(exc)) from exc

        contract_issues = collect_contract_issues(request)
        warnings: list[str] = list(contract_issues)
        warnings.extend(request.profile_context.warnings)
        warnings.extend(request.retrieved_evidence.warnings)
        if request.intent.assumptions:
            warnings.append(
                "Intent assumptions were preserved as unconfirmed and were not treated as verified requirements."
            )
        if request.intent.status == IntentStatus.UNABLE_TO_CLASSIFY:
            warnings.append(
                "Intent status is unable_to_classify. Service/task identity was not guessed for planning."
            )

        skeleton = build_deterministic_plan(request, warnings, contract_issues)
        planning_mode = PlanningMode.DETERMINISTIC_FALLBACK
        used_llm = False

        want_llm = self.allow_llm and request.model_mode != RequestedModelMode.DETERMINISTIC_FALLBACK
        if want_llm and not contract_issues:
            try:
                adjusted, rationale = self._apply_model_adjustments(request, skeleton)
                problems = dag_errors(adjusted.steps)
                if problems:
                    warnings.append(
                        "Local model proposed an invalid dependency graph; deterministic order was kept."
                    )
                else:
                    skeleton = adjusted
                    planning_mode = PlanningMode.OLLAMA
                    used_llm = True
                    if rationale:
                        warnings.append(f"Plan rationale: {rationale}")
            except (PlanningModelUnavailable, ValueError, ValidationError) as exc:
                warnings.append(f"Ollama plan proposal was not used ({exc}). Labeled deterministic_fallback.")

        if not used_llm:
            planning_mode = PlanningMode.DETERMINISTIC_FALLBACK
            if want_llm:
                if not any("deterministic_fallback" in w.casefold() or "ollama" in w.casefold() for w in warnings):
                    warnings.append("Ollama was unavailable or skipped. This plan is a deterministic_fallback.")

        skeleton = skeleton.model_copy(update={"planning_mode": planning_mode, "warnings": _dedupe(warnings)})
        plan, _ = sanitize_plan(skeleton, request, contract_issues)
        return WorkflowPlan.model_validate(plan.model_dump())

    def _apply_model_adjustments(
        self, request: WorkflowPlanningRequest, skeleton: WorkflowPlan
    ) -> tuple[WorkflowPlan, str]:
        compact = compact_planning_input(request, skeleton)
        completion = self.ollama.propose_plan_adjustments(compact)
        payload = extract_json_object(completion.content)
        rationale = " ".join(str(payload.get("plan_rationale") or "").split())[:280]
        adjustments = payload.get("step_adjustments") or []
        if not isinstance(adjustments, list):
            raise ValueError("Model JSON step_adjustments was not a list.")
        by_id = {step.step_id: step for step in skeleton.steps}
        updated: list[PlanStep] = []
        for step in skeleton.steps:
            match = next((item for item in adjustments if isinstance(item, dict) and item.get("step_id") == step.step_id), None)
            if not match:
                updated.append(step)
                continue
            title = str(match.get("title") or step.title).strip() or step.title
            description = str(match.get("description") or step.description).strip() or step.description
            depends_raw = match.get("depends_on", step.depends_on)
            if not isinstance(depends_raw, list):
                depends_raw = step.depends_on
            depends = [str(x).strip() for x in depends_raw if str(x).strip() in by_id and str(x).strip() != step.step_id]
            sequence = step.sequence
            raw_seq = match.get("sequence")
            if isinstance(raw_seq, int) and raw_seq >= 1:
                sequence = raw_seq
            updated.append(
                step.model_copy(
                    update={
                        "title": title[:120],
                        "description": description,
                        "depends_on": depends,
                        "sequence": sequence,
                    }
                )
            )
        return skeleton.model_copy(update={"steps": updated}), rationale


def create_workflow_plan(request: WorkflowPlanningRequest) -> WorkflowPlan:
    return WorkflowPlanningAgent().create_workflow_plan(request)


def build_deterministic_plan(
    request: WorkflowPlanningRequest,
    warnings: list[str],
    contract_issues: list[str],
) -> WorkflowPlan:
    intent = request.intent
    profile = request.profile_context
    evidence = request.retrieved_evidence
    prior = request.current_workflow_state
    plan_id = prior.plan_id if prior else f"plan-{intent.request_id}"
    plan_version = (prior.plan_version + 1) if prior else 1

    if contract_issues:
        failed_step = PlanStep(
            step_id="planning-blocked",
            sequence=1,
            title="Planning blocked by contract mismatch",
            description=(
                "Upstream IntentResult, ProfileContextResult, and RetrievedEvidenceResult "
                "do not share compatible IDs, service/task/jurisdiction, or contract versions. "
                "No personalized plan was created."
            ),
            step_type=StepType.OTHER,
            status=StepStatus.BLOCKED,
            blocking_reason="; ".join(contract_issues),
            requires_user_action=True,
            human_review_note="Fix the originating request IDs and re-run Agents 1–3 rather than guessing a plan.",
        )
        return WorkflowPlan(
            contract_version=CONTRACT_VERSION,
            planning_request_id=request.planning_request_id,
            request_id=intent.request_id,
            service_name=intent.service_name,
            document_type=intent.document_type,
            task_type=intent.task_type,
            jurisdiction=intent.jurisdiction,
            language=intent.language,
            plan_id=plan_id,
            plan_version=plan_version,
            plan_status=PlanStatus.FAILED,
            goal_summary=intent.normalized_goal,
            steps=[failed_step],
            missing_information=_missing_information(intent, profile, [], []),
            unresolved_conflicts=_conflicts(profile, [], []),
            evidence_gaps=[],
            warnings=_dedupe(warnings),
            human_approval_points=[],
            created_at=utc_now(),
            planning_mode=PlanningMode.DETERMINISTIC_FALLBACK,
        )

    requirements = valid_requirements(evidence)
    steps: list[PlanStep] = []
    sequence = 1

    review_evidence = [eid for req in requirements for eid in req.evidence_ids]
    if not review_evidence:
        review_evidence = [item.evidence_id for item in evidence.evidence]
    review_status = StepStatus.READY if review_evidence else StepStatus.BLOCKED
    review_support = (
        EvidenceSupportStatus.PARTIAL
        if review_evidence
        else EvidenceSupportStatus.NONE
    )
    if any(r.source_status == RequirementSourceStatus.CONFLICTING_OFFICIAL_SOURCES for r in requirements):
        review_support = EvidenceSupportStatus.CONFLICTING
    elif any(r.source_status == RequirementSourceStatus.OFFICIAL_CURRENT_CHECKED for r in requirements):
        review_support = EvidenceSupportStatus.SUPPORTED if requirements else review_support

    review = PlanStep(
        step_id="review-official-requirements",
        sequence=sequence,
        title="Review official requirements",
        description=(
            "Review the official procedure excerpts retrieved for this service and task. "
            "Do not treat this plan as proof that every portal field is listed."
        ),
        step_type=StepType.REVIEW_REQUIREMENTS,
        status=review_status,
        evidence_ids=review_evidence,
        evidence_status=review_support,
        blocking_reason=None if review_evidence else "No official evidence records were supplied for review.",
        requires_user_action=True,
        human_review_note="Read the cited official excerpts before preparing any application data.",
    )
    steps.append(review)
    sequence += 1
    last_id = review.step_id

    mentioned_keys = set()
    for req in requirements:
        mentioned_keys.update(fact_keys_mentioned(req.statement, profile))
        mentioned_keys.update(implied_fact_keys(req.statement))
    confirmed_keyset = {fact.key for fact in confirmed_facts(profile)}
    confirm_facts = [
        fact
        for fact in unconfirmed_facts(profile)
        if fact.key in mentioned_keys or fact.key in profile.missing_requested_facts
    ]
    confirm_keys = [fact.key for fact in confirm_facts]
    for key in mentioned_keys:
        if key not in confirmed_keyset and key not in confirm_keys:
            confirm_keys.append(key)
    if confirm_keys or profile.missing_requested_facts or profile.questions_for_user:
        confirm = PlanStep(
            step_id="confirm-unconfirmed-profile-facts",
            sequence=sequence,
            title="Confirm unconfirmed personal facts",
            description=(
                "Confirm candidate profile facts before they are used as prerequisites. "
                "Only user_confirmed facts may satisfy a plan prerequisite. "
                "Document-extracted, inferred, or unknown values remain unconfirmed."
            ),
            step_type=StepType.VERIFY_INFORMATION,
            status=StepStatus.NEEDS_USER_INPUT,
            depends_on=[last_id],
            required_fact_keys=confirm_keys + list(profile.missing_requested_facts),
            required_document_refs=document_refs_for_keys(profile, confirm_keys),
            evidence_ids=[],
            evidence_status=EvidenceSupportStatus.NONE,
            requires_user_action=True,
            human_review_note="Confirm or skip each unconfirmed fact. Values are not sent to any government site by this agent.",
        )
        steps.append(confirm)
        last_id = confirm.step_id
        sequence += 1

    requirement_steps: list[PlanStep] = []
    for req in requirements:
        step = _requirement_step(req, profile, sequence, last_id)
        requirement_steps.append(step)
        steps.append(step)
        sequence += 1
        last_id = step.step_id

    if not requirements:
        placeholder = PlanStep(
            step_id="await-official-requirement-evidence",
            sequence=sequence,
            title="Await official requirement evidence",
            description=(
                "No RequirementCandidate records with valid evidence_ids were available. "
                "Official fees, documents, deadlines, and eligibility rules were not invented."
            ),
            step_type=StepType.OTHER,
            status=StepStatus.BLOCKED,
            depends_on=[last_id],
            evidence_status=EvidenceSupportStatus.NONE,
            blocking_reason="RetrievedEvidenceResult did not contain citable requirement candidates.",
            requires_user_action=True,
            human_review_note="Re-run Information Retrieval or consult the official portal; this agent will not guess rules.",
        )
        steps.append(placeholder)
        last_id = placeholder.step_id
        sequence += 1

    approval = PlanStep(
        step_id="human-approval-before-portal",
        sequence=sequence,
        title="Explicit approval before portal action",
        description=(
            "Pause for an explicit user checkpoint before any login, form fill, payment, "
            "appointment booking, or submission. This plan is not permission to act."
        ),
        step_type=StepType.HUMAN_APPROVAL,
        status=StepStatus.NOT_STARTED,
        depends_on=[last_id],
        evidence_ids=review_evidence,
        evidence_status=review_support if review_evidence else EvidenceSupportStatus.NONE,
        requires_user_action=True,
        requires_explicit_approval=True,
        consequential_action=True,
        human_review_note="Approve only the next permitted step IDs. Do not treat remaining steps as authorized.",
    )
    steps.append(approval)
    sequence += 1

    portal_evidence = review_evidence
    portal = PlanStep(
        step_id="user-controlled-portal-action",
        sequence=sequence,
        title="User-controlled official portal action",
        description=_portal_description(intent, requirements),
        step_type=StepType.MANUAL_USER_ACTION,
        status=StepStatus.NOT_STARTED,
        depends_on=[approval.step_id],
        required_fact_keys=[f.key for f in confirmed_facts(profile)],
        evidence_ids=portal_evidence,
        evidence_status=review_support if portal_evidence else EvidenceSupportStatus.NONE,
        blocking_reason=None if portal_evidence else "No official evidence supports a portal procedure step.",
        requires_user_action=True,
        requires_explicit_approval=True,
        consequential_action=True,
        human_review_note="The user (or a later Execution Agent with approved step IDs only) performs this action. This agent does not open a browser.",
        assumptions=_constraint_assumptions(request),
    )
    if not portal_evidence:
        portal = portal.model_copy(update={"status": StepStatus.BLOCKED})
    steps.append(portal)
    sequence += 1

    verify = PlanStep(
        step_id="verify-completion",
        sequence=sequence,
        title="Verify completion with the user",
        description=(
            "Confirm with the user whether the selected approved action actually finished. "
            "Do not claim the government task is complete unless later monitoring observes it."
        ),
        step_type=StepType.VERIFY_COMPLETION,
        status=StepStatus.NOT_STARTED,
        depends_on=[portal.step_id],
        requires_user_action=True,
        human_review_note="Ask what the portal showed. Do not invent a completion status.",
    )
    steps.append(verify)
    sequence += 1

    track = PlanStep(
        step_id="track-status",
        sequence=sequence,
        title="Track later status locally",
        description=(
            "Keep a local record of pending versus observed portal status after execution. "
            "Observed facts must stay distinct from assumptions."
        ),
        step_type=StepType.TRACK_STATUS,
        status=StepStatus.NOT_STARTED,
        depends_on=[verify.step_id],
        requires_user_action=False,
        human_review_note="A later Monitoring Agent should timestamp observations. This step is not a completion claim.",
    )
    steps.append(track)

    if intent.status in {IntentStatus.NEEDS_CLARIFICATION, IntentStatus.UNABLE_TO_CLASSIFY}:
        for step in steps:
            if step.step_id in {"review-official-requirements", "confirm-unconfirmed-profile-facts"}:
                continue
            if step.status in {StepStatus.READY, StepStatus.NOT_STARTED} and step.step_type not in {
                StepType.HUMAN_APPROVAL,
                StepType.VERIFY_COMPLETION,
                StepType.TRACK_STATUS,
            }:
                step.status = StepStatus.NEEDS_USER_INPUT
                step.blocking_reason = step.blocking_reason or (
                    "Intent still has clarification_questions or could not classify the task; service/task identity is not assumed."
                )

    missing = _missing_information(intent, profile, steps, request.user_constraints)
    conflicts = _conflicts(profile, requirements, steps)
    gaps = _evidence_gaps(evidence, requirements, steps)

    if any(c.topic.startswith("official") for c in conflicts):
        for step in steps:
            if step.evidence_status == EvidenceSupportStatus.CONFLICTING:
                step.status = StepStatus.BLOCKED
                step.blocking_reason = step.blocking_reason or (
                    "Official sources conflict; this step is blocked pending user review. No value was guessed."
                )

    return WorkflowPlan(
        contract_version=CONTRACT_VERSION,
        planning_request_id=request.planning_request_id,
        request_id=intent.request_id,
        service_name=intent.service_name,
        document_type=intent.document_type,
        task_type=intent.task_type,
        jurisdiction=intent.jurisdiction,
        language=intent.language,
        plan_id=plan_id,
        plan_version=plan_version,
        plan_status=PlanStatus.PARTIAL,
        goal_summary=intent.normalized_goal,
        steps=steps,
        missing_information=missing,
        unresolved_conflicts=conflicts,
        evidence_gaps=gaps,
        warnings=_dedupe(warnings),
        human_approval_points=[],
        created_at=utc_now(),
        planning_mode=PlanningMode.DETERMINISTIC_FALLBACK,
    )


def _requirement_step(
    req: RequirementCandidate,
    profile: ProfileContextResult,
    sequence: int,
    depends_on: str,
) -> PlanStep:
    support = evidence_status_for(req)
    keys = fact_keys_mentioned(req.statement, profile)
    confirmed_keyset = {fact.key for fact in confirmed_facts(profile)}
    unconfirmed_keys = [key for key in keys if key not in confirmed_keyset]
    step_type = _step_type_for_requirement(req.statement)
    consequential = looks_consequential(req.statement)
    status = StepStatus.READY
    blocking = None
    if support == EvidenceSupportStatus.CONFLICTING:
        status = StepStatus.BLOCKED
        blocking = "Cited official sources conflict for this requirement."
    elif unconfirmed_keys:
        status = StepStatus.NEEDS_USER_INPUT
        blocking = (
            "Depends on profile facts that are not user_confirmed: " + ", ".join(unconfirmed_keys)
        )
    return PlanStep(
        step_id=f"apply-requirement-{req.requirement_id}",
        sequence=sequence,
        title=_title_from_requirement(req.statement, req.requirement_id),
        description=req.statement,
        step_type=step_type,
        status=status,
        depends_on=[depends_on],
        required_fact_keys=keys,
        required_document_refs=document_refs_for_keys(profile, keys),
        evidence_ids=list(req.evidence_ids),
        evidence_status=support,
        blocking_reason=blocking,
        requires_user_action=True,
        requires_explicit_approval=consequential,
        consequential_action=consequential,
        human_review_note="Copied from a RequirementCandidate. Exact fees or deadlines appear only if the cited excerpt states them.",
        assumptions=[],
    )


def _step_type_for_requirement(statement: str) -> StepType:
    blob = statement.casefold()
    if any(token in blob for token in ("document", "proof", "photocop", "self-attest", "original")):
        return StepType.PREPARE_DOCUMENT
    if any(token in blob for token in ("form", "fill", "application", "user id", "register")):
        return StepType.PREPARE_FORM
    return StepType.OTHER


def _title_from_requirement(statement: str, requirement_id: str) -> str:
    text = " ".join(statement.strip().split())
    if len(text) <= 80:
        return text
    return text[:77] + "…"


def _portal_description(intent: IntentResult, requirements: list[RequirementCandidate]) -> str:
    service = intent.service_name or "the official service portal"
    task = intent.task_type.value
    if requirements:
        return (
            f"When explicitly approved, complete the user-controlled {task} action on {service} "
            "using only cited official steps. This agent does not log in, submit, or pay."
        )
    return (
        f"A later user-controlled {task} action on {service} may be needed, but official procedure "
        "evidence is currently insufficient to specify it."
    )


def _constraint_assumptions(request: WorkflowPlanningRequest) -> list[str]:
    assumptions: list[str] = []
    for key, value in request.user_constraints.items():
        assumptions.append(
            f"User-confirmed constraint {key}={value} is a preference, not an official government rule."
        )
    for item in request.intent.assumptions:
        assumptions.append(f"Intent assumption (unconfirmed): {item}")
    return assumptions


def _missing_information(
    intent: IntentResult,
    profile: ProfileContextResult,
    steps: list[PlanStep],
    user_constraints: dict[str, str],
) -> list[MissingInformationItem]:
    items: list[MissingInformationItem] = []
    blocking_ids = [s.step_id for s in steps if s.status in {StepStatus.NEEDS_USER_INPUT, StepStatus.BLOCKED}]
    for question in intent.clarification_questions:
        items.append(
            MissingInformationItem(
                fact_key=None,
                question=question,
                source="intent",
                status="clarification",
                blocks_step_ids=blocking_ids,
            )
        )
    for key in profile.missing_requested_facts:
        items.append(
            MissingInformationItem(
                fact_key=key,
                question=f"Requested profile fact '{key}' is not user_confirmed.",
                source="profile",
                status="blocking",
                blocks_step_ids=[s.step_id for s in steps if key in s.required_fact_keys] or blocking_ids,
            )
        )
    seen_keys = {item.fact_key for item in items if item.fact_key}
    for step in steps:
        for key in step.required_fact_keys:
            if key in seen_keys:
                continue
            fact = next((f for f in profile.relevant_facts if f.key == key), None)
            if fact and fact.status == FactStatus.USER_CONFIRMED and fact.confirmed_by_user:
                continue
            status = "unconfirmed" if fact else "unknown"
            items.append(
                MissingInformationItem(
                    fact_key=key,
                    question=(
                        f"Profile fact '{key}' has status {fact.status.value} and cannot satisfy a prerequisite."
                        if fact
                        else f"Official evidence mentions '{key}', but no user_confirmed value is available."
                    ),
                    source="profile" if fact else "planning",
                    status=status if fact else "blocking",
                    blocks_step_ids=[s.step_id for s in steps if key in s.required_fact_keys],
                )
            )
            seen_keys.add(key)
    for question in profile.questions_for_user:
        items.append(
            MissingInformationItem(
                fact_key=None,
                question=question,
                source="profile",
                status="unconfirmed",
                blocks_step_ids=[s.step_id for s in steps if s.step_type == StepType.VERIFY_INFORMATION],
            )
        )
    _ = user_constraints
    return items


def _conflicts(
    profile: ProfileContextResult,
    requirements: list[RequirementCandidate],
    steps: list[PlanStep],
) -> list[UnresolvedConflict]:
    items: list[UnresolvedConflict] = []
    for conflict in profile.conflicts:
        items.append(
            UnresolvedConflict(
                topic=f"profile:{conflict.key}",
                statement=conflict.note or f"Conflicting values for {conflict.key}: {', '.join(conflict.competing_values)}",
                source_refs=list(conflict.source_refs),
                affected_step_ids=[s.step_id for s in steps if conflict.key in s.required_fact_keys],
            )
        )
    for req in requirements:
        if req.source_status != RequirementSourceStatus.CONFLICTING_OFFICIAL_SOURCES:
            continue
        items.append(
            UnresolvedConflict(
                topic="official_sources",
                statement=req.statement,
                source_refs=list(req.evidence_ids),
                affected_step_ids=[s.step_id for s in steps if set(req.evidence_ids) & set(s.evidence_ids)],
            )
        )
    return items


def _evidence_gaps(evidence, requirements: list[RequirementCandidate], steps: list[PlanStep]) -> list[EvidenceGap]:
    gaps: list[EvidenceGap] = []
    for question in evidence.unanswered_questions:
        gaps.append(
            EvidenceGap(
                question=question,
                related_step_ids=["review-official-requirements", "await-official-requirement-evidence"]
                if not requirements
                else ["review-official-requirements"],
                note="Preserved from RetrievedEvidenceResult.unanswered_questions.",
            )
        )
    if not requirements:
        gaps.append(
            EvidenceGap(
                question="Which official requirements, fees, documents, and deadlines apply to this task?",
                related_step_ids=[s.step_id for s in steps if s.status == StepStatus.BLOCKED],
                note="No valid RequirementCandidate records were present.",
            )
        )
    if evidence.retrieval_status.value in {"no_evidence", "blocked", "failed"}:
        gaps.append(
            EvidenceGap(
                question="Official retrieval did not complete with usable evidence.",
                related_step_ids=["review-official-requirements"],
                note=f"retrieval_status={evidence.retrieval_status.value}",
            )
        )
    unclear = [req for req in requirements if req.jurisdiction_scope == "unknown"]
    if unclear:
        gaps.append(
            EvidenceGap(
                question="Which jurisdiction do the cited official requirements apply to?",
                related_step_ids=[f"apply-requirement-{req.requirement_id}" for req in unclear],
                note="RequirementCandidate.jurisdiction_scope is unknown. Intent jurisdiction was copied, not inferred.",
            )
        )
    return gaps


def compact_planning_input(request: WorkflowPlanningRequest, skeleton: WorkflowPlan) -> dict[str, Any]:
    """Structured, bounded payload. No full documents or private chain-of-thought."""
    profile = request.profile_context
    facts = []
    for fact in profile.relevant_facts:
        entry = {
            "key": fact.key,
            "status": fact.status.value,
            "confirmed_by_user": fact.confirmed_by_user,
            "source_ref": fact.source_ref,
        }
        if fact.sensitivity.value != "highly_sensitive":
            entry["value"] = fact.value
        facts.append(entry)
    return {
        "intent": {
            "request_id": request.intent.request_id,
            "normalized_goal": request.intent.normalized_goal,
            "service_name": request.intent.service_name,
            "document_type": request.intent.document_type,
            "task_type": request.intent.task_type.value,
            "jurisdiction": request.intent.jurisdiction,
            "language": request.intent.language,
            "clarification_questions": request.intent.clarification_questions,
            "assumptions": request.intent.assumptions,
        },
        "profile_fact_keys": facts,
        "user_constraints": request.user_constraints,
        "requirements": [
            {
                "requirement_id": req.requirement_id,
                "statement": req.statement,
                "evidence_ids": req.evidence_ids,
                "source_status": req.source_status.value,
            }
            for req in valid_requirements(request.retrieved_evidence)
        ],
        "retrieval_warnings": request.retrieved_evidence.warnings,
        "unanswered_questions": request.retrieved_evidence.unanswered_questions,
        "skeleton_steps": [
            {
                "step_id": step.step_id,
                "sequence": step.sequence,
                "title": step.title,
                "description": step.description,
                "step_type": step.step_type.value,
                "depends_on": step.depends_on,
                "evidence_ids": step.evidence_ids,
                "status": step.status.value,
            }
            for step in skeleton.steps
        ],
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key.casefold() in seen:
            continue
        seen.add(key.casefold())
        out.append(key)
    return out
