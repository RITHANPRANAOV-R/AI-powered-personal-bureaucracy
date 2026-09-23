"""Deterministic status precedence rules, evidence citation mapping, and Markdown formatting.

Enforces status truthfulness and ensures all factual claims cite valid evidence IDs.
"""

from __future__ import annotations

from typing import List, Tuple

from agents.compliance_validation.schema import ValidationDecision
from agents.execution_assistance.schema import ExecutionStatus
from agents.monitoring_update.schema import EventSourceType

from .schema import (
    CitizenNextStep,
    CitizenResponse,
    CompletedActionRecord,
    EvidenceReferenceMap,
    ImportantDetailRecord,
    MissingItemRecord,
    OfficialLinkRecord,
    OverallStatus,
    PendingActionRecord,
    ResponseGenerationRequest,
)


def calculate_overall_status(request: ResponseGenerationRequest) -> OverallStatus:
    """
    Determine the maximum allowable overall status using deterministic status precedence rules.
    Models cannot override this status.
    """
    val_res = request.validation_result
    exec_res = request.execution_result
    mon_res = request.monitoring_result

    # 1. Validation Block
    if val_res.decision == ValidationDecision.BLOCK or val_res.blocked_step_ids:
        return OverallStatus.BLOCKED

    # 2. Validation Needs User Input
    if val_res.decision == ValidationDecision.NEEDS_USER_INPUT:
        return OverallStatus.ACTION_REQUIRED

    # 3. Execution Status Precedence
    if exec_res:
        if exec_res.confirmation_observed:
            if mon_res and mon_res.monitoring_status.value in {"uncertain", "blocked"}:
                return OverallStatus.UNCERTAIN
            return OverallStatus.CONFIRMED
        if exec_res.execution_status == ExecutionStatus.UNCERTAIN:
            return OverallStatus.UNCERTAIN
        if exec_res.submission_attempted:
            return OverallStatus.SUBMITTED
        if exec_res.execution_status == ExecutionStatus.PREPARED_FOR_REVIEW:
            return OverallStatus.ACTION_REQUIRED

    # 4. Monitoring Status Precedence
    if mon_res:
        if mon_res.portal_observed_status == "confirmed":
            return OverallStatus.CONFIRMED
        if mon_res.monitoring_status.value == "uncertain":
            return OverallStatus.UNCERTAIN
        if mon_res.monitoring_status.value == "needs_user_update":
            return OverallStatus.ACTION_REQUIRED

    # 5. Plan Step Analysis
    ready_steps = [s for s in request.workflow_plan.steps if s.status.value == "ready"]
    completed_steps = [s for s in request.workflow_plan.steps if s.status.value == "completed"]

    if len(completed_steps) == len(request.workflow_plan.steps) and completed_steps:
        return OverallStatus.COMPLETED
    if ready_steps or completed_steps:
        return OverallStatus.IN_PROGRESS

    return OverallStatus.NOT_STARTED


def extract_completed_actions(request: ResponseGenerationRequest) -> List[CompletedActionRecord]:
    actions: List[CompletedActionRecord] = []
    plan = request.workflow_plan
    exec_res = request.execution_result
    mon_res = request.monitoring_result

    for step in plan.steps:
        if step.status.value == "completed":
            source_ref = f"plan:{plan.plan_id}"
            if exec_res:
                exec_step = next((s for s in exec_res.step_results if s.step_id == step.step_id), None)
                if exec_step:
                    source_ref = f"execution:{exec_res.execution_request_id}"
            actions.append(
                CompletedActionRecord(
                    action_title=step.title,
                    status="completed",
                    source_reference=source_ref,
                    completed_at=plan.created_at,
                )
            )

    if mon_res:
        for s_mon in mon_res.step_statuses:
            if s_mon.current_status in {"completed", "confirmed"} and not any(a.action_title.endswith(s_mon.step_id) for a in actions):
                actions.append(
                    CompletedActionRecord(
                        action_title=f"Step {s_mon.step_id}",
                        status=s_mon.current_status,
                        source_reference=f"{s_mon.last_source_type.value}:{s_mon.last_event_id}",
                        completed_at=s_mon.last_updated_at,
                    )
                )

    return actions


def extract_pending_actions(request: ResponseGenerationRequest) -> List[PendingActionRecord]:
    pending: List[PendingActionRecord] = []
    plan = request.workflow_plan
    val_res = request.validation_result

    for step in plan.steps:
        if step.status.value in {"not_started", "ready", "needs_user_input", "blocked"}:
            assigned = "user" if step.requires_user_action or step.status.value == "needs_user_input" else "execution_agent"
            reason = step.blocking_reason or f"Step is currently {step.status.value}."
            pending.append(
                PendingActionRecord(
                    step_id=step.step_id,
                    action_title=step.title,
                    reason=reason,
                    assigned_to=assigned,
                )
            )

    return pending


def extract_citizen_next_step(request: ResponseGenerationRequest) -> CitizenNextStep:
    val_res = request.validation_result
    plan = request.workflow_plan

    # Check for approval checkpoints
    if val_res.required_user_approvals:
        chk = val_res.required_user_approvals[0]
        return CitizenNextStep(
            title=f"Provide Explicit Approval for Step '{chk.step_id}'",
            description=f"Action '{chk.description}' requires explicit user terminal approval with phrase '{chk.required_phrase}'.",
            action_type="explicit_approval",
            required_user_phrase=chk.required_phrase,
        )

    # Check for unconfirmed facts / missing items
    unconfirmed = [f for f in request.profile_context.relevant_facts if not f.confirmed_by_user]
    if unconfirmed:
        fact = unconfirmed[0]
        return CitizenNextStep(
            title=f"Confirm Personal Fact: {fact.key}",
            description=f"Fact '{fact.key}' is currently {fact.status.value}. Confirm value '{fact.value}' before execution.",
            action_type="user_action",
        )

    # Check for ready step
    ready_step = next((s for s in plan.steps if s.status.value == "ready"), None)
    if ready_step:
        return CitizenNextStep(
            title=ready_step.title,
            description=ready_step.description,
            action_type="user_action" if ready_step.requires_user_action else "review",
        )

    return CitizenNextStep(
        title="Review Workflow Progress",
        description="Review your plan progress or check the official portal for status updates.",
        action_type="review",
    )


def extract_official_links(request: ResponseGenerationRequest) -> List[OfficialLinkRecord]:
    links: List[OfficialLinkRecord] = []
    evidence = request.retrieved_evidence

    for ev in evidence.evidence:
        if ev.source_url and not any(l.url == ev.source_url for l in links):
            links.append(
                OfficialLinkRecord(
                    title=ev.source_title or ev.source_host,
                    url=ev.source_url,
                    related_evidence_ids=[ev.evidence_id],
                )
            )

    return links


def build_evidence_references(request: ResponseGenerationRequest) -> List[EvidenceReferenceMap]:
    refs: List[EvidenceReferenceMap] = []
    evidence = request.retrieved_evidence

    for req in evidence.requirements_found:
        refs.append(
            EvidenceReferenceMap(
                claim_statement=req.statement,
                evidence_ids=req.evidence_ids,
                source_type="official_evidence",
            )
        )

    return refs


def render_markdown_response(
    request: ResponseGenerationRequest,
    status: OverallStatus,
    summary: str,
    next_step: CitizenNextStep,
    completed: List[CompletedActionRecord],
    pending: List[PendingActionRecord],
    official_links: List[OfficialLinkRecord],
    evidence_refs: List[EvidenceReferenceMap],
) -> str:
    lang = request.response_language or request.intent.language or "English"
    lines: List[str] = []

    lines.append(f"# {request.intent.service_name or 'Official Bureaucracy'} Guidance Summary")
    lines.append(f"**Overall Status**: `{status.value.upper()}` | **Language**: {lang}\n")

    lines.append("## Summary")
    lines.append(f"{summary}\n")

    if next_step:
        lines.append("## Immediate Next Step")
        lines.append(f"**{next_step.title}**")
        lines.append(f"{next_step.description}")
        if next_step.required_user_phrase:
            lines.append(f"> Required Terminal Approval Phrase: `{next_step.required_user_phrase}`")
        lines.append("")

    if completed:
        lines.append("## Completed Actions")
        for act in completed:
            lines.append(f"- **{act.action_title}** (`{act.status}`) — Source: `{act.source_reference}`")
        lines.append("")

    if pending:
        lines.append("## Outstanding / Pending Steps")
        for p in pending:
            lines.append(f"- **[{p.step_id}] {p.action_title}** (Assigned: {p.assigned_to}) — {p.reason}")
        lines.append("")

    if official_links:
        lines.append("## Official Portal References")
        for link in official_links:
            lines.append(f"- [{link.title}]({link.url}) (Evidence: {', '.join(link.related_evidence_ids)})")
        lines.append("")

    if evidence_refs:
        lines.append("## Grounded Evidence Citations")
        for ref in evidence_refs:
            lines.append(f"- \"{ref.claim_statement}\" (Cited Evidence IDs: {', '.join(ref.evidence_ids)})")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by AI Personal Bureaucracy Assistant — Response Generation Agent.*")

    return "\n".join(lines)
