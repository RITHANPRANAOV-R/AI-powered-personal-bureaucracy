from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable

from .schema import (
    ApprovalPoint,
    EvidenceSupport,
    MissingInformationItem,
    PlanStatus,
    PlanStep,
    StepStatus,
    StepType,
    WorkflowPlan,
    WorkflowPlanningRequest,
)


SUPPORTED_TARGETS = {
    "address",
    "mobile_number",
    "email",
    "name",
    "date_of_birth",
    "gender",
    "biometric",
}

SUPPORTED_INTENTS = {"update_request", "correction_request", "enrollment", "status_inquiry"}


def create_workflow_plan(request: WorkflowPlanningRequest) -> WorkflowPlan:
    """Build an evidence-grounded plan without retrieval or execution side effects."""
    request = WorkflowPlanningRequest.model_validate(request)
    intent = request.intent
    retrieval = request.retrieved_evidence
    warnings = [item.message for item in retrieval.warnings]
    known_evidence = {item.evidence_id: item for item in retrieval.evidence}
    all_evidence_ids = sorted(known_evidence)

    if retrieval.request_id != intent.session_id:
        warnings.append("Retrieval request_id does not match the intent session_id.")

    task, target = _resolve_task(intent.intent_type, intent.update_type, request.session_state)
    missing = _missing_information(request)
    steps: list[PlanStep] = []
    conflicts = [f"{item.topic}: {item.description}" for item in retrieval.conflicts]

    if retrieval.domain.casefold() != "aadhaar":
        warnings.append("Workflow Planning currently supports only the Aadhaar domain.")
        return _build_plan(
            request,
            task="unsupported",
            target=target,
            status=PlanStatus.BLOCKED,
            steps=[],
            missing=missing,
            approvals=[],
            evidence_ids=all_evidence_ids,
            conflicts=conflicts,
            warnings=warnings,
        )

    if task == "unsupported":
        missing.append(
            MissingInformationItem(
                field_name=None,
                question="Clarify which supported Aadhaar task should be planned.",
                source="intent",
                required=True,
            )
        )
        return _build_plan(
            request,
            task=task,
            target=target,
            status=PlanStatus.NEEDS_USER_INPUT,
            steps=[],
            missing=missing,
            approvals=[],
            evidence_ids=all_evidence_ids,
            conflicts=conflicts,
            warnings=warnings,
        )

    requirement_steps, evidence_gaps = _requirement_steps(retrieval.requirements, known_evidence)
    if not retrieval.requirements:
        evidence_gaps.append(
            MissingInformationItem(
                question="Retrieved evidence did not provide any applicable Aadhaar requirements.",
                source="evidence",
                required=True,
            )
        )
    if all_evidence_ids:
        steps.append(
            PlanStep(
                step_id="review-retrieved-evidence",
                sequence=1,
                title="Review retrieved Aadhaar evidence",
                description="Review the cited authoritative evidence before using it as a workflow prerequisite.",
                step_type=StepType.REVIEW_EVIDENCE,
                status=StepStatus.READY,
                evidence_ids=all_evidence_ids,
                evidence_support=EvidenceSupport.SUPPORTED,
                requires_user_action=False,
            )
        )

    steps.extend(requirement_steps)
    if steps and steps[0].step_id == "review-retrieved-evidence":
        for step in steps[1:]:
            if not step.depends_on:
                step.depends_on = [steps[0].step_id]

    for gap in evidence_gaps:
        missing.append(gap)

    if task == "status_inquiry":
        if not steps:
            missing.append(
                MissingInformationItem(
                    question="No retrieved Aadhaar status guidance is available.",
                    source="evidence",
                    required=True,
                )
            )
    elif steps and not evidence_gaps:
        approval = PlanStep(
            step_id="review-before-aadhaar-action",
            sequence=len(steps) + 1,
            title="Review the proposed Aadhaar action",
            description="Review the evidence-backed steps and confirm the intended Aadhaar action before a downstream execution component acts.",
            step_type=StepType.HUMAN_APPROVAL,
            status=StepStatus.NOT_STARTED,
            depends_on=[step.step_id for step in steps],
            evidence_ids=all_evidence_ids,
            evidence_support=EvidenceSupport.SUPPORTED,
            requires_user_action=True,
            requires_explicit_approval=True,
        )
        steps.append(approval)
        action = PlanStep(
            step_id="perform-aadhaar-action",
            sequence=len(steps) + 1,
            title=f"Perform Aadhaar {target or task} action",
            description="A downstream execution component may perform this described action only after separate compliance validation and authorization.",
            step_type=StepType.USER_ACTION,
            status=StepStatus.NOT_STARTED,
            depends_on=[approval.step_id],
            evidence_ids=all_evidence_ids,
            evidence_support=EvidenceSupport.SUPPORTED,
            requires_user_action=True,
        )
        steps.append(action)

    steps = _normalize_and_validate_dag(steps, warnings)
    approvals = _approval_points(steps)
    status = _derive_status(task, steps, missing, evidence_gaps, conflicts)
    return _build_plan(
        request,
        task=task,
        target=target,
        status=status,
        steps=steps,
        missing=missing,
        approvals=approvals,
        evidence_ids=all_evidence_ids,
        conflicts=conflicts,
        warnings=warnings,
    )


def validate_dependency_graph(steps: Iterable[PlanStep]) -> list[str]:
    """Return deterministic dependency errors without mutating the steps."""
    items = list(steps)
    ids = [step.step_id for step in items]
    errors: list[str] = []
    if len(ids) != len(set(ids)):
        errors.append("Duplicate step IDs are not allowed.")
    known = set(ids)
    graph: dict[str, list[str]] = defaultdict(list)
    indegree = {step.step_id: 0 for step in items}
    for step in items:
        for dependency in step.depends_on:
            if dependency not in known:
                errors.append(f"Step '{step.step_id}' depends on unknown step '{dependency}'.")
            elif dependency == step.step_id:
                errors.append(f"Step '{step.step_id}' cannot depend on itself.")
            else:
                graph[dependency].append(step.step_id)
                indegree[step.step_id] += 1
    queue = deque(step_id for step_id, degree in indegree.items() if degree == 0)
    visited: list[str] = []
    while queue:
        current = queue.popleft()
        visited.append(current)
        for child in graph[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(visited) != len(items):
        errors.append("Dependency graph contains a cycle.")
    position = {step_id: index for index, step_id in enumerate(visited)}
    for step in items:
        for dependency in step.depends_on:
            if dependency in position and position[dependency] >= position.get(step.step_id, -1):
                errors.append(f"Step '{step.step_id}' is ordered before dependency '{dependency}'.")
    return errors


def repair_dependency_graph(steps: Iterable[PlanStep]) -> list[PlanStep]:
    """Repair invalid dependencies by applying deterministic sequence order."""
    ordered = sorted(steps, key=lambda item: (item.sequence, item.step_id))
    repaired: list[PlanStep] = []
    previous: str | None = None
    for sequence, step in enumerate(ordered, start=1):
        repaired.append(step.model_copy(update={"sequence": sequence, "depends_on": [previous] if previous else []}))
        previous = step.step_id
    return repaired


def _resolve_task(intent_type: str, update_type: str | None, session_state: Any) -> tuple[str, str | None]:
    target = update_type
    if target is None and session_state is not None:
        target = session_state.update_type
    if intent_type in {"update_request", "correction_request"} and target in SUPPORTED_TARGETS:
        return "update", target
    if intent_type == "enrollment":
        return "enrollment", None
    if intent_type == "status_inquiry":
        return "status_inquiry", None
    return "unsupported", target


def _requirement_steps(requirements: list[dict[str, Any]], evidence: dict[str, Any]) -> tuple[list[PlanStep], list[MissingInformationItem]]:
    steps: list[PlanStep] = []
    gaps: list[MissingInformationItem] = []
    for index, raw in enumerate(requirements, start=1):
        requirement_id = str(raw.get("requirement_id") or raw.get("id") or f"requirement-{index}").strip()
        text = str(raw.get("description") or raw.get("statement") or raw.get("query") or "").strip()
        if not text:
            continue
        requested_ids = raw.get("evidence_ids", [])
        if not isinstance(requested_ids, list):
            requested_ids = []
        valid_ids = [str(item) for item in requested_ids if str(item) in evidence]
        invalid_ids = [str(item) for item in requested_ids if str(item) not in evidence]
        if invalid_ids:
            gaps.append(
                MissingInformationItem(
                    question=f"Requirement '{requirement_id}' references unavailable evidence.",
                    source="evidence",
                    required=True,
                )
            )
        if not valid_ids:
            valid_ids = _linked_evidence_ids(requirement_id, raw, evidence)
        if not valid_ids:
            gaps.append(
                MissingInformationItem(
                    question=f"No authoritative evidence supports requirement '{text}'.",
                    source="evidence",
                    required=True,
                )
            )
            continue
        category = str(raw.get("category") or "requirement").casefold()
        step_type = StepType.PREPARE_DOCUMENT if any(word in category or word in text.casefold() for word in ("document", "proof")) else StepType.PREPARE_INFORMATION
        steps.append(
            PlanStep(
                step_id=f"requirement-{requirement_id}",
                sequence=len(steps) + 2,
                title=f"Address Aadhaar requirement: {category}",
                description=text,
                step_type=step_type,
                status=StepStatus.READY,
                evidence_ids=valid_ids,
                evidence_support=EvidenceSupport.SUPPORTED,
                requires_user_action=True,
            )
        )
    return steps, gaps


def _linked_evidence_ids(requirement_id: str, requirement: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    category = str(requirement.get("category") or "").casefold()
    linked: list[str] = []
    for evidence_id, item in evidence.items():
        associated = item.metadata.get("associated_requirements", [])
        item_category = str(item.metadata.get("category") or "").casefold()
        if requirement_id in associated or (category and item_category == category):
            linked.append(evidence_id)
    return sorted(set(linked))


def _missing_information(request: WorkflowPlanningRequest) -> list[MissingInformationItem]:
    items: list[MissingInformationItem] = []
    sources = [request.intent.missing_information]
    if request.session_state is not None:
        sources.append(request.session_state.missing_information)
    seen: set[tuple[str, str]] = set()
    for source_items in sources:
        for item in source_items:
            key = (item.field_name, item.reason)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                MissingInformationItem(
                    field_name=item.field_name,
                    question=item.reason,
                    source="intent" if source_items is sources[0] else "session",
                    required=item.required,
                )
            )
    return items


def _normalize_and_validate_dag(steps: list[PlanStep], warnings: list[str]) -> list[PlanStep]:
    errors = validate_dependency_graph(steps)
    if errors:
        warnings.extend(errors)
        steps = repair_dependency_graph(steps)
    errors = validate_dependency_graph(steps)
    if errors:
        warnings.extend(errors)
        return []
    return [step.model_copy(update={"sequence": index}) for index, step in enumerate(steps, start=1)]


def _approval_points(steps: list[PlanStep]) -> list[ApprovalPoint]:
    return [
        ApprovalPoint(
            approval_id=f"approval-{step.step_id}",
            step_id=step.step_id,
            reason="The described Aadhaar action requires separate human review before downstream execution.",
            confirmation="Confirm the intended step after compliance review; this is not execution authorization.",
        )
        for step in steps
        if step.step_type == StepType.HUMAN_APPROVAL
    ]


def _derive_status(task: str, steps: list[PlanStep], missing: list[MissingInformationItem], gaps: list[MissingInformationItem], conflicts: list[str]) -> PlanStatus:
    if task == "unsupported" or not steps:
        return PlanStatus.NEEDS_USER_INPUT if missing and task != "unsupported" else PlanStatus.BLOCKED
    if gaps or conflicts:
        return PlanStatus.PARTIAL
    if any(item.required for item in missing):
        return PlanStatus.NEEDS_USER_INPUT
    return PlanStatus.READY


def _build_plan(request: WorkflowPlanningRequest, *, task: str, target: str | None, status: PlanStatus, steps: list[PlanStep], missing: list[MissingInformationItem], approvals: list[ApprovalPoint], evidence_ids: list[str], conflicts: list[str], warnings: list[str]) -> WorkflowPlan:
    retrieval = request.retrieved_evidence
    return WorkflowPlan(
        planning_request_id=request.planning_request_id,
        request_id=request.intent.session_id,
        session_id=request.intent.session_id,
        domain=retrieval.domain,
        service=retrieval.service,
        task=task,
        target=target,
        plan_status=status,
        steps=steps,
        missing_information=missing,
        approval_points=approvals,
        evidence_ids=evidence_ids,
        conflicts=conflicts,
        warnings=list(dict.fromkeys(warnings)),
    )