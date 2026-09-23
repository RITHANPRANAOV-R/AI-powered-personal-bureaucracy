"""Auditable deterministic policy rule functions for Compliance & Validation Agent.

No LLM calls are made here. All rules are pure, auditable Python functions.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from agents.information_retrieval.schema import RequirementSourceStatus, RetrievedEvidenceResult
from agents.intent_understanding.schema import IntentResult
from agents.user_context.schema import FactStatus, ProfileContextResult
from agents.workflow_planning.schema import PlanStep, StepStatus, WorkflowPlan

from .schema import (
    ComplianceValidationRequest,
    ExecutionObservation,
    IssueCategory,
    IssueSeverity,
    StepValidationDecision,
    StepValidationResult,
    UserApprovalCheckpoint,
    UserApprovalRecord,
    ValidationIssue,
    ValidationPhase,
)


SECRET_KEYWORDS = re.compile(
    r"\b(password|otp|captcha|pin|cvv|secret_key|auth_token|recovery_code)\b",
    re.IGNORECASE,
)
CONSEQUENTIAL_KEYWORDS = re.compile(
    r"\b(submit|registration|register|account creation|payment|pay|book appointment|appointment|send document|share document|upload document)\b",
    re.IGNORECASE,
)


def validate_contract_and_provenance(
    request: ComplianceValidationRequest,
) -> Tuple[List[ValidationIssue], List[str]]:
    """
    Validate contract version alignment, correlation IDs, service/task/jurisdiction,
    cited evidence existence, official host allowlist, and evidence status.
    """
    issues: List[ValidationIssue] = []
    passed_rule_ids: List[str] = []

    intent = request.intent
    profile = request.profile_context
    evidence = request.retrieved_evidence
    plan = request.workflow_plan

    # 1. Contract versions
    versions = {
        "intent": intent.contract_version,
        "profile": profile.contract_version,
        "evidence": evidence.contract_version,
        "plan": plan.contract_version,
        "request": request.contract_version,
    }
    if any(v != "1.0" for v in versions.values()):
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.CONTRACT_MISMATCH,
                message=f"Unsupported contract version in upstream objects: {versions}",
                required_resolution="Ensure all upstream agents generate contract_version='1.0'.",
            )
        )
    else:
        passed_rule_ids.append("RULE_CONTRACT_VERSION_1.0")

    # 2. Correlation IDs
    if not (
        intent.request_id
        == profile.intent_request_id
        == evidence.intent_request_id
        == plan.request_id
    ):
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.CONTRACT_MISMATCH,
                message=(
                    f"Request ID correlation mismatch: intent={intent.request_id}, "
                    f"profile={profile.intent_request_id}, evidence={evidence.intent_request_id}, "
                    f"plan={plan.request_id}"
                ),
                required_resolution="Ensure request_id correlates across all upstream results.",
            )
        )
    else:
        passed_rule_ids.append("RULE_CORRELATION_ID_MATCH")

    # 3. Service / Task / Jurisdiction consistency
    services = {
        s for s in [intent.service_name, profile.service_name, evidence.service_name, plan.service_name] if s
    }
    if len(services) > 1:
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.CONTRACT_MISMATCH,
                message=f"Inconsistent service_name across upstream results: {services}",
                required_resolution="Resolve service_name discrepancies before validating plan.",
            )
        )
    else:
        passed_rule_ids.append("RULE_SERVICE_CONSISTENCY")

    tasks = {intent.task_type, profile.task_type, evidence.task_type, plan.task_type}
    if len(tasks) > 1:
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.CONTRACT_MISMATCH,
                message=f"Inconsistent task_type across upstream results: {[t.value for t in tasks]}",
                required_resolution="Ensure task_type is consistent across all agent contracts.",
            )
        )
    else:
        passed_rule_ids.append("RULE_TASK_CONSISTENCY")

    jurisdictions = {
        j for j in [intent.jurisdiction, profile.jurisdiction, evidence.jurisdiction, plan.jurisdiction] if j
    }
    if len(jurisdictions) > 1:
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.WARNING,
                category=IssueCategory.CONTRACT_MISMATCH,
                message=f"Jurisdiction discrepancy across contracts: {jurisdictions}",
                required_resolution="Verify location/jurisdiction alignment across profile and evidence.",
            )
        )
    else:
        passed_rule_ids.append("RULE_JURISDICTION_CONSISTENCY")

    # 4. Evidence existence and host allowlist
    known_evidence: Dict[str, str] = {e.evidence_id: e.source_host for e in evidence.evidence}
    allowed_hosts = set(request.allowed_source_hosts)

    missing_evidence_ids: Set[str] = set()
    disallowed_host_evidence_ids: Set[str] = set()

    for step in plan.steps:
        for eid in step.evidence_ids:
            if eid not in known_evidence:
                missing_evidence_ids.add(eid)
            else:
                host = known_evidence[eid]
                if host and host not in allowed_hosts and not any(host.endswith("." + ah) for ah in allowed_hosts):
                    disallowed_host_evidence_ids.add(eid)

    if missing_evidence_ids:
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.EVIDENCE_MISSING,
                message=f"Plan cites evidence IDs not present in RetrievedEvidenceResult: {sorted(missing_evidence_ids)}",
                evidence_ids=sorted(missing_evidence_ids),
                required_resolution="Re-run Information Retrieval or remove uncited evidence references from plan.",
            )
        )
    else:
        passed_rule_ids.append("RULE_EVIDENCE_EXISTENCE")

    if disallowed_host_evidence_ids:
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.SOURCE_NOT_ALLOWED,
                message=f"Plan cites evidence from hosts not in allowlist ({allowed_hosts}): {sorted(disallowed_host_evidence_ids)}",
                evidence_ids=sorted(disallowed_host_evidence_ids),
                required_resolution="Ensure requirement evidence comes strictly from allowlisted official hosts.",
            )
        )
    else:
        passed_rule_ids.append("RULE_OFFICIAL_HOST_ALLOWLIST")

    # 5. Requirement source status checks
    for req in evidence.requirements_found:
        if req.source_status == RequirementSourceStatus.OFFICIAL_DATE_UNCLEAR:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.WARNING,
                    category=IssueCategory.UNSUPPORTED_CLAIM,
                    message=f"Requirement candidate '{req.requirement_id}' has official_date_unclear status.",
                    evidence_ids=req.evidence_ids,
                    required_resolution="User review required for time-sensitive official rules.",
                )
            )
        elif req.source_status == RequirementSourceStatus.CONFLICTING_OFFICIAL_SOURCES:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.UNSUPPORTED_CLAIM,
                    message=f"Requirement candidate '{req.requirement_id}' has conflicting_official_sources status.",
                    evidence_ids=req.evidence_ids,
                    required_resolution="Resolve conflicting official requirement sources before plan review.",
                )
            )

    return issues, passed_rule_ids


def validate_facts_and_dependencies(
    request: ComplianceValidationRequest,
) -> Tuple[List[ValidationIssue], List[str]]:
    """
    Validate fact verification status (only user_confirmed facts satisfy prerequisites)
    and verify step DAG (no duplicate step IDs, missing step IDs, or cycles).
    """
    issues: List[ValidationIssue] = []
    passed_rule_ids: List[str] = []

    profile = request.profile_context
    plan = request.workflow_plan

    # 1. Fact Verification Status Check
    confirmed_fact_keys = {
        fact.key for fact in profile.relevant_facts if fact.status == FactStatus.USER_CONFIRMED and fact.confirmed_by_user
    }

    unconfirmed_fact_issues: List[str] = []
    for step in plan.steps:
        for key in step.required_fact_keys:
            if key not in confirmed_fact_keys:
                unconfirmed_fact_issues.append(f"Step '{step.step_id}' requires unconfirmed fact '{key}'")
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.NEEDS_USER_INPUT,
                        category=IssueCategory.FACT_UNCONFIRMED,
                        message=(
                            f"Step '{step.step_id}' requires fact '{key}', which is not user_confirmed. "
                            f"(Document-extracted, inferred, or unknown facts cannot satisfy prerequisites)."
                        ),
                        affected_step_ids=[step.step_id],
                        fact_keys=[key],
                        required_resolution=f"Obtain explicit user confirmation for fact key '{key}'.",
                    )
                )

    if not unconfirmed_fact_issues:
        passed_rule_ids.append("RULE_ALL_PREREQUISITE_FACTS_CONFIRMED")

    # 2. Step ID uniqueness and DAG validation
    step_ids: Set[str] = set()
    duplicate_step_ids: Set[str] = set()
    step_map: Dict[str, PlanStep] = {}

    for step in plan.steps:
        if step.step_id in step_ids:
            duplicate_step_ids.add(step.step_id)
        step_ids.add(step.step_id)
        step_map[step.step_id] = step

    if duplicate_step_ids:
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.DEPENDENCY_INVALID,
                message=f"Duplicate step IDs found in plan: {sorted(duplicate_step_ids)}",
                affected_step_ids=sorted(duplicate_step_ids),
                required_resolution="Ensure every step in WorkflowPlan has a unique step_id.",
            )
        )

    # Check dependency references
    missing_deps: Dict[str, List[str]] = {}
    for step in plan.steps:
        for dep in step.depends_on:
            if dep not in step_map:
                missing_deps.setdefault(step.step_id, []).append(dep)

    if missing_deps:
        for sid, mdeps in missing_deps.items():
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.DEPENDENCY_INVALID,
                    message=f"Step '{sid}' depends on non-existent step IDs: {mdeps}",
                    affected_step_ids=[sid],
                    required_resolution="Fix step dependency graph references.",
                )
            )

    # Check for cycles using DFS
    visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
    cycle_found = False

    def dfs(node_id: str, path: List[str]):
        nonlocal cycle_found
        visited[node_id] = 1
        step = step_map.get(node_id)
        if step:
            for dep in step.depends_on:
                if dep in step_map:
                    if visited.get(dep, 0) == 1:
                        cycle_found = True
                        cycle_path = path + [dep]
                        issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.BLOCKER,
                                category=IssueCategory.DEPENDENCY_INVALID,
                                message=f"Cycle detected in step dependency graph: {' -> '.join(cycle_path)}",
                                affected_step_ids=cycle_path,
                                required_resolution="Remove cycle from plan step dependencies.",
                            )
                        )
                    elif visited.get(dep, 0) == 0:
                        dfs(dep, path + [dep])
        visited[node_id] = 2

    for sid in step_ids:
        if visited.get(sid, 0) == 0:
            dfs(sid, [sid])

    if not duplicate_step_ids and not missing_deps and not cycle_found:
        passed_rule_ids.append("RULE_DAG_VALIDITY_ACYCLIC")

    # Dependency status propagation check
    for step in plan.steps:
        if step.status == StepStatus.READY:
            for dep in step.depends_on:
                parent = step_map.get(dep)
                if parent and parent.status in {StepStatus.BLOCKED, StepStatus.NEEDS_USER_INPUT}:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.BLOCKER,
                            category=IssueCategory.DEPENDENCY_INVALID,
                            message=(
                                f"Step '{step.step_id}' is marked READY but depends on step '{dep}' "
                                f"which has status {parent.status.value}."
                            ),
                            affected_step_ids=[step.step_id, dep],
                            required_resolution="Set dependent step status to BLOCKED or NEEDS_USER_INPUT.",
                        )
                    )

    return issues, passed_rule_ids


def validate_consequential_actions_and_approvals(
    request: ComplianceValidationRequest,
) -> Tuple[List[ValidationIssue], List[UserApprovalCheckpoint], List[str]]:
    """
    Identify consequential external actions, check explicit user approval checkpoints,
    enforce exact approval phrase for Passport Seva registration, inspect credential safety,
    and prevent duplicate submission risks.
    """
    issues: List[ValidationIssue] = []
    checkpoints: List[UserApprovalCheckpoint] = []
    passed_rule_ids: List[str] = []

    intent = request.intent
    plan = request.workflow_plan
    user_approvals = {appr.step_id: appr for appr in request.user_approvals if appr.confirmed_by_user}

    # 1. Consequential Action Checkpoints & Passport Seva specific checks
    is_passport_seva = (
        (intent.service_name and "passport" in intent.service_name.lower())
        or (plan.service_name and "passport" in plan.service_name.lower())
    )

    for step in plan.steps:
        is_consequential = (
            step.consequential_action
            or step.requires_explicit_approval
            or (
                step.step_type.value not in {"review_requirements", "verify_information", "track_status", "verify_completion"}
                and bool(CONSEQUENTIAL_KEYWORDS.search(step.title + " " + step.description))
            )
        )

        if is_consequential:
            required_phrase = f"APPROVE STEP {step.step_id}"
            if is_passport_seva and ("register" in step.step_id.lower() or "submit" in step.step_id.lower() or "portal" in step.step_id.lower()):
                required_phrase = "SUBMIT PASSPORT SEVA REGISTRATION"

            checkpoints.append(
                UserApprovalCheckpoint(
                    approval_id=f"chk-{step.step_id}",
                    step_id=step.step_id,
                    required_phrase=required_phrase,
                    description=f"Explicit user approval checkpoint for consequential step: {step.title}",
                )
            )

            # Check if valid approval record exists
            approval_rec = user_approvals.get(step.step_id)
            if not approval_rec:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.NEEDS_USER_INPUT,
                        category=IssueCategory.APPROVAL_MISSING,
                        message=(
                            f"Step '{step.step_id}' ({step.title}) is a consequential action requiring "
                            f"explicit user approval with phrase '{required_phrase}' before execution."
                        ),
                        affected_step_ids=[step.step_id],
                        required_resolution=f"User must provide explicit approval record with phrase '{required_phrase}'.",
                    )
                )
            else:
                if approval_rec.exact_approval_phrase.strip() != required_phrase and approval_rec.exact_approval_phrase.strip() != f"APPROVE STEP {step.step_id}":
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.BLOCKER,
                            category=IssueCategory.APPROVAL_MISSING,
                            message=(
                                f"Step '{step.step_id}' approval record phrase '{approval_rec.exact_approval_phrase}' "
                                f"does not match required approval phrase '{required_phrase}'."
                            ),
                            affected_step_ids=[step.step_id],
                            approval_ids=[approval_rec.approval_id],
                            required_resolution=f"Provide approval record with exact phrase '{required_phrase}'.",
                        )
                    )
                else:
                    passed_rule_ids.append(f"RULE_CONSEQUENTIAL_APPROVAL_{step.step_id}")

    # 2. Authentication Secrets & Credentials Safety Gate
    secret_findings: List[str] = []
    for step in plan.steps:
        blob = f"{step.title} {step.description} {' '.join(step.required_fact_keys)}"
        match = SECRET_KEYWORDS.search(blob)
        if match:
            secret_findings.append(f"Step '{step.step_id}' mentions secret keyword '{match.group()}'")
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.OUT_OF_SCOPE_ACTION,
                    message=(
                        f"Step '{step.step_id}' contains authentication secrets keyword '{match.group()}'. "
                        f"No agent may read, request, type, store, or log authentication credentials, OTPs, or CAPTCHAs."
                    ),
                    affected_step_ids=[step.step_id],
                    required_resolution="Secrets must be handled manually by the user. Remove secret references from automated plan steps.",
                )
            )

    if not secret_findings:
        passed_rule_ids.append("RULE_CREDENTIAL_SAFETY_NO_SECRETS")

    return issues, checkpoints, passed_rule_ids


def validate_post_execution_observations(
    request: ComplianceValidationRequest,
) -> Tuple[List[ValidationIssue], List[str]]:
    """
    Validate observed actions against plan steps, host allowlist, explicit approvals,
    duplicate submission risks, and handle uncertain states.
    """
    issues: List[ValidationIssue] = []
    passed_rule_ids: List[str] = []

    if request.validation_phase != ValidationPhase.POST_EXECUTION and not request.execution_observations:
        return issues, ["RULE_PRE_EXECUTION_SKIPPED_OBSERVATION_CHECKS"]

    plan = request.workflow_plan
    step_ids = {s.step_id for s in plan.steps}
    allowed_hosts = set(request.allowed_source_hosts)
    approvals_by_step = {a.step_id: a for a in request.user_approvals if a.confirmed_by_user}

    attempted_submissions = 0

    for obs in request.execution_observations:
        # Check step reference
        if obs.step_id not in step_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.OUT_OF_SCOPE_ACTION,
                    message=f"Execution observation '{obs.observation_id}' references unplanned step ID '{obs.step_id}'.",
                    affected_step_ids=[obs.step_id],
                    required_resolution="Execution agent must only execute steps present in the validated plan.",
                )
            )

        # Check host allowlist
        if obs.target_host and obs.target_host not in allowed_hosts and not any(obs.target_host.endswith("." + ah) for ah in allowed_hosts):
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.SOURCE_NOT_ALLOWED,
                    message=f"Observed action navigated to disallowed host '{obs.target_host}'.",
                    affected_step_ids=[obs.step_id],
                    required_resolution="Execution agent must restrict navigation strictly to allowed official hosts.",
                )
            )

        # Check approval match
        if obs.step_id not in approvals_by_step:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.APPROVAL_MISSING,
                    message=f"Execution observation '{obs.observation_id}' for step '{obs.step_id}' lacked explicit user approval.",
                    affected_step_ids=[obs.step_id],
                    required_resolution="Do not execute steps without explicit user approval record.",
                )
            )

        # Track submission attempts
        if "submit" in obs.action_type.lower() or obs.status in {"attempted", "uncertain"}:
            attempted_submissions += 1
            if obs.status == "uncertain":
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.NEEDS_USER_INPUT,
                        category=IssueCategory.UNCERTAIN_RESULT,
                        message=f"Execution observation for step '{obs.step_id}' has ambiguous/uncertain status.",
                        affected_step_ids=[obs.step_id],
                        required_resolution="Require manual portal inspection by user before proceeding or retrying.",
                    )
                )

    if attempted_submissions > 1:
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.DUPLICATE_SUBMISSION_RISK,
                message=f"Multiple submission attempts detected ({attempted_submissions}). Auto-retry is strictly prohibited.",
                required_resolution="Require manual user inspection of portal state before any repeat attempt.",
            )
        )

    if not issues and request.execution_observations:
        passed_rule_ids.append("RULE_POST_EXECUTION_OBSERVATIONS_VALID")

    return issues, passed_rule_ids
