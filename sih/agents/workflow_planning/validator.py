"""Deterministic contract, evidence, DAG, and approval-gate checks.

The local model may propose titles and order. This module is the authority
for whether a WorkflowPlan may be returned.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable, Optional

from agents.information_retrieval.schema import (
    RequirementCandidate,
    RequirementSourceStatus,
    RetrievedEvidenceResult,
)
from agents.intent_understanding.schema import IntentResult
from agents.user_context.schema import FactStatus, ProfileContextResult, ProfileFact

from .schema import (
    CONTRACT_VERSION,
    SUPPORTED_UPSTREAM_CONTRACT_VERSIONS,
    EvidenceSupportStatus,
    HumanApprovalPoint,
    PlanStatus,
    PlanStep,
    StepStatus,
    StepType,
    WorkflowPlan,
    WorkflowPlanningRequest,
)

RULE_BEARING_STEP_TYPES = {
    StepType.PREPARE_DOCUMENT,
    StepType.PREPARE_FORM,
    StepType.MANUAL_USER_ACTION,
    StepType.OTHER,
}

CONSEQUENTIAL_HINTS = (
    "pay",
    "payment",
    "fee",
    "submit",
    "appointment",
    "book",
    "login",
    "register",
    "upload",
    "portal",
)

STATEMENT_FACT_HINTS = {
    "email": ("e-mail", "email id", "e-mail id", "email"),
    "full_name": ("name", "user id details"),
    "mobile": ("mobile", "phone number", "mobile number"),
    "date_of_birth": ("date of birth", "dob", "birth"),
}


def _norm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped.casefold() if stripped else None


def collect_contract_issues(request: WorkflowPlanningRequest) -> list[str]:
    issues: list[str] = []
    intent = request.intent
    profile = request.profile_context
    evidence = request.retrieved_evidence

    for label, version in (
        ("request", request.contract_version),
        ("intent", intent.contract_version),
        ("profile_context", profile.contract_version),
        ("retrieved_evidence", evidence.contract_version),
    ):
        if version not in SUPPORTED_UPSTREAM_CONTRACT_VERSIONS:
            issues.append(
                f"Unsupported contract_version on {label}: {version!r}. Supported: {CONTRACT_VERSION}."
            )

    if intent.request_id != profile.intent_request_id:
        issues.append(
            f"intent.request_id ({intent.request_id}) != profile_context.intent_request_id "
            f"({profile.intent_request_id})."
        )
    if intent.request_id != evidence.intent_request_id:
        issues.append(
            f"intent.request_id ({intent.request_id}) != retrieved_evidence.intent_request_id "
            f"({evidence.intent_request_id})."
        )
    if profile.request_id != evidence.profile_context_request_id:
        issues.append(
            f"profile_context.request_id ({profile.request_id}) != "
            f"retrieved_evidence.profile_context_request_id ({evidence.profile_context_request_id})."
        )

    if intent.task_type != profile.task_type:
        issues.append(
            f"task_type mismatch: intent={intent.task_type.value}, profile={profile.task_type.value}."
        )
    if intent.task_type != evidence.task_type:
        issues.append(
            f"task_type mismatch: intent={intent.task_type.value}, evidence={evidence.task_type.value}."
        )

    issues.extend(
        _optional_field_mismatch("service_name", intent.service_name, profile.service_name, evidence.service_name)
    )
    issues.extend(
        _optional_field_mismatch("jurisdiction", intent.jurisdiction, profile.jurisdiction, evidence.jurisdiction)
    )
    return issues


def _optional_field_mismatch(field: str, intent_val: Optional[str], profile_val: Optional[str], evidence_val: Optional[str]) -> list[str]:
    present = [(label, value) for label, value in (("intent", intent_val), ("profile", profile_val), ("evidence", evidence_val)) if _norm(value)]
    if len(present) < 2:
        return []
    canonical = present[0][1]
    issues: list[str] = []
    for label, value in present[1:]:
        if _norm(value) != _norm(canonical):
            issues.append(
                f"{field} mismatch across upstream results: intent={intent_val!r}, "
                f"profile={profile_val!r}, evidence={evidence_val!r}. Values were not overwritten."
            )
            break
    return issues


def known_evidence_ids(evidence: RetrievedEvidenceResult) -> set[str]:
    return {item.evidence_id for item in evidence.evidence}


def valid_requirements(evidence: RetrievedEvidenceResult) -> list[RequirementCandidate]:
    known = known_evidence_ids(evidence)
    valid: list[RequirementCandidate] = []
    for req in evidence.requirements_found:
        statement = (req.statement or "").strip()
        if not statement:
            continue
        cited = [eid for eid in req.evidence_ids if eid in known]
        if cited:
            valid.append(req.model_copy(update={"evidence_ids": cited}))
    return valid


def evidence_status_for(requirement: RequirementCandidate) -> EvidenceSupportStatus:
    if requirement.source_status == RequirementSourceStatus.CONFLICTING_OFFICIAL_SOURCES:
        return EvidenceSupportStatus.CONFLICTING
    if requirement.source_status == RequirementSourceStatus.OFFICIAL_DATE_UNCLEAR:
        return EvidenceSupportStatus.PARTIAL
    return EvidenceSupportStatus.SUPPORTED


def confirmed_facts(profile: ProfileContextResult) -> list[ProfileFact]:
    return [
        fact
        for fact in profile.relevant_facts
        if fact.status == FactStatus.USER_CONFIRMED and fact.confirmed_by_user
    ]


def unconfirmed_facts(profile: ProfileContextResult) -> list[ProfileFact]:
    return [
        fact
        for fact in profile.relevant_facts
        if fact.status in {FactStatus.DOCUMENT_EXTRACTED, FactStatus.INFERRED, FactStatus.UNKNOWN}
        or not fact.confirmed_by_user
    ]


def document_refs_for_keys(profile: ProfileContextResult, keys: Iterable[str]) -> list[str]:
    wanted = set(keys)
    refs: list[str] = []
    seen: set[str] = set()
    for fact in profile.relevant_facts:
        if fact.key not in wanted:
            continue
        ref = (fact.source_ref or "").strip()
        if not ref or ref in seen or ref.startswith("/") or ":\\" in ref:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs


def implied_fact_keys(requirement_text: str) -> list[str]:
    blob = requirement_text.casefold()
    keys: list[str] = []
    for key, aliases in STATEMENT_FACT_HINTS.items():
        if any(alias in blob for alias in aliases):
            keys.append(key)
    return keys


def fact_keys_mentioned(requirement_text: str, profile: ProfileContextResult) -> list[str]:
    blob = requirement_text.casefold()
    keys: list[str] = []
    for fact in profile.relevant_facts:
        token = fact.key.replace("_", " ")
        if fact.key in blob or token in blob:
            keys.append(fact.key)
            continue
        aliases = STATEMENT_FACT_HINTS.get(fact.key, ())
        if any(alias in blob for alias in aliases):
            keys.append(fact.key)
    for key in implied_fact_keys(requirement_text):
        if key not in keys:
            keys.append(key)
    return keys


def looks_consequential(text: str) -> bool:
    blob = text.casefold()
    return any(hint in blob for hint in CONSEQUENTIAL_HINTS)


def dag_errors(steps: list[PlanStep]) -> list[str]:
    errors: list[str] = []
    ids = [step.step_id for step in steps]
    seen: set[str] = set()
    for step_id in ids:
        if step_id in seen:
            errors.append(f"Duplicate step_id: {step_id}")
        seen.add(step_id)
    id_set = set(ids)
    for step in steps:
        for dep in step.depends_on:
            if dep not in id_set:
                errors.append(f"Step {step.step_id} depends on missing step_id {dep}")
            if dep == step.step_id:
                errors.append(f"Step {step.step_id} depends on itself")
    graph: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {step.step_id: 0 for step in steps}
    for step in steps:
        for dep in step.depends_on:
            if dep in id_set and dep != step.step_id:
                graph[dep].append(step.step_id)
                indegree[step.step_id] += 1
    queue = deque([sid for sid, degree in indegree.items() if degree == 0])
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for nxt in graph[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if steps and visited != len(steps):
        errors.append("Cyclic depends_on graph")
    return errors


def strip_invalid_evidence(steps: list[PlanStep], known_ids: set[str], warnings: list[str]) -> list[PlanStep]:
    cleaned: list[PlanStep] = []
    for step in steps:
        valid_ids = [eid for eid in step.evidence_ids if eid in known_ids]
        dropped = [eid for eid in step.evidence_ids if eid not in known_ids]
        if dropped:
            warnings.append(
                f"Removed unknown evidence_ids from {step.step_id}: {', '.join(dropped)}."
            )
        update: dict = {"evidence_ids": valid_ids}
        if not valid_ids:
            if step.step_type in RULE_BEARING_STEP_TYPES:
                update["evidence_status"] = EvidenceSupportStatus.NONE
                update["status"] = StepStatus.BLOCKED
                update["blocking_reason"] = (
                    step.blocking_reason
                    or "This step would state an official requirement, fee, deadline, or procedure without a cited evidence_id from the current RetrievedEvidenceResult."
                )
            else:
                update["evidence_status"] = EvidenceSupportStatus.NONE
        cleaned.append(step.model_copy(update=update))
    return cleaned


def forbid_completed_future_work(steps: list[PlanStep], prior: Optional[WorkflowPlan], warnings: list[str]) -> list[PlanStep]:
    prior_completed = set()
    if prior:
        prior_completed = {s.step_id for s in prior.steps if s.status == StepStatus.COMPLETED}
    cleaned: list[PlanStep] = []
    for step in steps:
        if step.status == StepStatus.COMPLETED and step.step_id not in prior_completed:
            warnings.append(
                f"Step {step.step_id} was marked completed without prior execution state; reset to not_started."
            )
            cleaned.append(step.model_copy(update={"status": StepStatus.NOT_STARTED}))
        elif step.status == StepStatus.IN_PROGRESS and step.step_id not in prior_completed:
            cleaned.append(step.model_copy(update={"status": StepStatus.NOT_STARTED}))
        else:
            cleaned.append(step)
    return cleaned


def enforce_approval_gates(steps: list[PlanStep]) -> list[PlanStep]:
    updated: list[PlanStep] = []
    for step in steps:
        if step.consequential_action or step.step_type == StepType.HUMAN_APPROVAL:
            updated.append(
                step.model_copy(
                    update={
                        "requires_explicit_approval": True,
                    }
                )
            )
        else:
            updated.append(step)
    return updated


def rebuild_approval_points(steps: list[PlanStep]) -> list[HumanApprovalPoint]:
    points: list[HumanApprovalPoint] = []
    for step in steps:
        if not (step.requires_explicit_approval or step.consequential_action or step.step_type == StepType.HUMAN_APPROVAL):
            continue
        points.append(
            HumanApprovalPoint(
                approval_id=f"approve-{step.step_id}",
                step_id=step.step_id,
                reason="Consequential external or government-facing action requires an explicit user checkpoint. A plan is not execution authorization.",
                what_user_must_confirm=step.human_review_note or step.description,
            )
        )
    return points


def repair_depends_on(steps: list[PlanStep]) -> list[PlanStep]:
    """If DAG is invalid, fall back to sequence order."""
    if not dag_errors(steps):
        return steps
    ordered = sorted(steps, key=lambda s: (s.sequence, s.step_id))
    repaired: list[PlanStep] = []
    prev: Optional[str] = None
    for index, step in enumerate(ordered, start=1):
        depends = [prev] if prev else []
        repaired.append(step.model_copy(update={"sequence": index, "depends_on": depends}))
        prev = step.step_id
    return repaired


def derive_plan_status(
    *,
    contract_issues: list[str],
    steps: list[PlanStep],
    missing: list,
    conflicts: list,
    gaps: list,
    intent: IntentResult,
) -> PlanStatus:
    if contract_issues:
        return PlanStatus.FAILED
    if any(step.status == StepStatus.BLOCKED for step in steps) and conflicts:
        if not any(step.status in {StepStatus.READY, StepStatus.NEEDS_USER_INPUT, StepStatus.NOT_STARTED} for step in steps if step.step_type not in {StepType.HUMAN_APPROVAL, StepType.VERIFY_COMPLETION, StepType.TRACK_STATUS}):
            return PlanStatus.BLOCKED
    if intent.clarification_questions or any(step.status == StepStatus.NEEDS_USER_INPUT for step in steps) or missing:
        blocking_missing = [item for item in missing if getattr(item, "status", "") in {"blocking", "clarification"}]
        if blocking_missing or intent.clarification_questions or any(step.status == StepStatus.NEEDS_USER_INPUT for step in steps):
            if gaps or any(step.status == StepStatus.BLOCKED for step in steps):
                return PlanStatus.NEEDS_USER_INPUT if not _all_rule_steps_blocked(steps) else PlanStatus.BLOCKED
            return PlanStatus.NEEDS_USER_INPUT
    if gaps or any(step.status == StepStatus.BLOCKED for step in steps) or any(step.evidence_status in {EvidenceSupportStatus.PARTIAL, EvidenceSupportStatus.NONE, EvidenceSupportStatus.CONFLICTING} for step in steps if step.evidence_ids or step.step_type in RULE_BEARING_STEP_TYPES):
        if _all_rule_steps_blocked(steps) and not any(s.evidence_ids for s in steps):
            return PlanStatus.BLOCKED
        return PlanStatus.PARTIAL
    return PlanStatus.READY


def _all_rule_steps_blocked(steps: list[PlanStep]) -> bool:
    rule_steps = [s for s in steps if s.step_type in RULE_BEARING_STEP_TYPES]
    return bool(rule_steps) and all(s.status == StepStatus.BLOCKED for s in rule_steps)


def sanitize_plan(plan: WorkflowPlan, request: WorkflowPlanningRequest, contract_issues: list[str]) -> tuple[WorkflowPlan, list[str]]:
    warnings = list(plan.warnings)
    known = known_evidence_ids(request.retrieved_evidence)
    steps = strip_invalid_evidence(plan.steps, known, warnings)
    steps = forbid_completed_future_work(steps, request.current_workflow_state, warnings)
    steps = enforce_approval_gates(steps)
    dag_problems = dag_errors(steps)
    if dag_problems:
        warnings.extend(dag_problems)
        steps = repair_depends_on(steps)
        leftover = dag_errors(steps)
        if leftover:
            warnings.extend(leftover)
            steps = []
            contract_issues = list(contract_issues) + leftover
    points = rebuild_approval_points(steps)
    status = derive_plan_status(
        contract_issues=contract_issues,
        steps=steps,
        missing=plan.missing_information,
        conflicts=plan.unresolved_conflicts,
        gaps=plan.evidence_gaps,
        intent=request.intent,
    )
    sanitized = plan.model_copy(
        update={
            "steps": steps,
            "human_approval_points": points,
            "warnings": _dedupe(warnings),
            "plan_status": status if not contract_issues else PlanStatus.FAILED,
        }
    )
    leftover = dag_errors(sanitized.steps)
    if leftover and sanitized.steps:
        raise ValueError("Plan DAG remained invalid after repair: " + "; ".join(leftover))
    return sanitized, leftover


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
