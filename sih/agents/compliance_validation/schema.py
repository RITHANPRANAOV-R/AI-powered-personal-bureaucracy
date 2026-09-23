"""Pydantic contracts for the Compliance & Validation Agent.

Upstream contracts IntentResult, ProfileContextResult, RetrievedEvidenceResult,
and WorkflowPlan are imported unchanged from their respective packages.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.information_retrieval.schema import RetrievedEvidenceResult
from agents.intent_understanding.schema import IntentResult
from agents.user_context.schema import ProfileContextResult
from agents.workflow_planning.schema import WorkflowPlan


CONTRACT_VERSION = "1.0"
POLICY_VERSION = "1.0.0"
DEFAULT_ALLOWED_HOSTS = ["passportindia.gov.in", "www.passportindia.gov.in"]


class ValidationPhase(str, Enum):
    PRE_EXECUTION = "pre_execution"
    POST_EXECUTION = "post_execution"


class ValidationDecision(str, Enum):
    APPROVE = "approve"
    NEEDS_USER_INPUT = "needs_user_input"
    BLOCK = "block"


class StepValidationDecision(str, Enum):
    APPROVE = "approve"
    NEEDS_USER_INPUT = "needs_user_input"
    BLOCK = "block"


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    NEEDS_USER_INPUT = "needs_user_input"
    BLOCKER = "blocker"


class IssueCategory(str, Enum):
    CONTRACT_MISMATCH = "contract_mismatch"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    EVIDENCE_MISSING = "evidence_missing"
    SOURCE_NOT_ALLOWED = "source_not_allowed"
    FACT_UNCONFIRMED = "fact_unconfirmed"
    DEPENDENCY_INVALID = "dependency_invalid"
    APPROVAL_MISSING = "approval_missing"
    OUT_OF_SCOPE_ACTION = "out_of_scope_action"
    DUPLICATE_SUBMISSION_RISK = "duplicate_submission_risk"
    EXECUTION_MISMATCH = "execution_mismatch"
    UNCERTAIN_RESULT = "uncertain_result"


class UserApprovalRecord(BaseModel):
    """Explicit user confirmation passed from the CLI or orchestrator."""

    model_config = ConfigDict(extra="ignore")

    approval_id: str = Field(default_factory=lambda: f"appr-{uuid4().hex[:8]}")
    step_id: str = Field(description="Step ID this approval applies to")
    exact_approval_phrase: str = Field(description="User approval phrase or command string")
    timestamp: str = Field(description="ISO-8601 timestamp when approval was given")
    scope: str = Field(default="step_execution", description="Scope of approval")
    confirmed_by_user: bool = Field(default=True, description="Must be explicitly True")


class ExecutionObservation(BaseModel):
    """Observed action status passed from a future Execution & Assistance Agent."""

    model_config = ConfigDict(extra="ignore")

    observation_id: str = Field(default_factory=lambda: f"obs-{uuid4().hex[:8]}")
    step_id: str = Field(description="Validated step ID being observed")
    action_type: str = Field(description="Action type, e.g. navigate, form_fill, submit")
    target_host: str = Field(description="Host domain where action occurred")
    observed_at: str = Field(description="ISO-8601 timestamp")
    status: str = Field(description="attempted, confirmed, failed, or uncertain")
    details: str = Field(default="", description="Observed status details")
    source_type: str = Field(default="browser_observation", description="Observation source")


class ComplianceValidationRequest(BaseModel):
    """Public input contract for `validate_workflow`."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Contract version. Initial value is 1.0.",
    )
    validation_request_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID for this validation pass.",
    )
    validation_phase: ValidationPhase = Field(
        default=ValidationPhase.PRE_EXECUTION,
        description="Pre-execution plan check vs post-execution observation check.",
    )
    intent: IntentResult
    profile_context: ProfileContextResult
    retrieved_evidence: RetrievedEvidenceResult
    workflow_plan: WorkflowPlan
    requested_step_ids: List[str] = Field(
        default_factory=list,
        description="Optional subset of steps to validate. Empty means validate all steps.",
    )
    user_approvals: List[UserApprovalRecord] = Field(
        default_factory=list,
        description="User approval records passed in by CLI/orchestrator.",
    )
    execution_observations: List[ExecutionObservation] = Field(
        default_factory=list,
        description="Observed execution records for post-execution validation.",
    )
    allowed_source_hosts: List[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_HOSTS),
        description="Allowed host registry for official evidence and actions.",
    )
    policy_version: str = Field(
        default=POLICY_VERSION,
        description="Version string for the deterministic policy rules.",
    )


class StepValidationResult(BaseModel):
    """Validation result for an individual plan step."""

    model_config = ConfigDict(extra="ignore")

    step_id: str
    decision: StepValidationDecision
    passed_rule_ids: List[str] = Field(default_factory=list)
    failed_rule_ids: List[str] = Field(default_factory=list)
    cited_evidence_ids: List[str] = Field(default_factory=list)
    required_confirmed_fact_keys: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    """Actionable diagnostic issue produced by policy evaluation."""

    model_config = ConfigDict(extra="ignore")

    issue_id: str = Field(default_factory=lambda: f"issue-{uuid4().hex[:8]}")
    severity: IssueSeverity
    category: IssueCategory
    message: str
    affected_step_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    fact_keys: List[str] = Field(default_factory=list)
    approval_ids: List[str] = Field(default_factory=list)
    required_resolution: str = Field(description="Action needed to resolve the issue")


class UserApprovalCheckpoint(BaseModel):
    """Description of an approval checkpoint required before execution."""

    model_config = ConfigDict(extra="ignore")

    approval_id: str
    step_id: str
    required_phrase: str
    description: str


class ValidationResult(BaseModel):
    """
    Canonical output contract of the Compliance & Validation Agent.

    `decision = approve` ONLY means the plan is eligible for user review.
    `execution_authorized` is ALWAYS false.
    """

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Contract version. Initial value is 1.0.",
    )
    validation_request_id: str = Field(description="Validation pass correlation ID")
    request_id: str = Field(description="Originating Intent request_id")
    plan_id: str = Field(description="Workflow plan ID being validated")
    plan_version: int = Field(ge=1, description="Workflow plan version")
    validation_phase: ValidationPhase = Field(description="pre_execution or post_execution")
    decision: ValidationDecision = Field(
        description="approve, needs_user_input, or block"
    )
    decision_scope: str = Field(
        default=(
            "approve means only 'plan is eligible to be shown for user review'. "
            "It does NOT authorize execution or form submission."
        ),
        description="Explicit meaning of the decision",
    )
    eligible_for_user_review: bool = Field(
        description="Whether the plan may be presented to the user for human review",
    )
    eligible_step_ids: List[str] = Field(
        default_factory=list,
        description="Steps that passed deterministic checks and may be shown for review",
    )
    blocked_step_ids: List[str] = Field(
        default_factory=list,
        description="Steps that failed compliance checks and must not proceed",
    )
    step_results: List[StepValidationResult] = Field(
        default_factory=list,
        description="Individual validation result per step",
    )
    issues: List[ValidationIssue] = Field(
        default_factory=list,
        description="Actionable compliance and safety issues",
    )
    required_user_approvals: List[UserApprovalCheckpoint] = Field(
        default_factory=list,
        description="Approval checkpoints still required from the user",
    )
    execution_authorized: bool = Field(
        default=False,
        description="ALWAYS false. The validator never grants authorization to execute.",
    )
    validated_at: str = Field(description="ISO-8601 timestamp of validation")
    policy_version: str = Field(default=POLICY_VERSION)
    summary: str = Field(description="Concise user-facing explanation")

    @field_validator("execution_authorized")
    @classmethod
    def _must_be_false(cls, v: bool) -> bool:
        if v:
            raise ValueError("execution_authorized must always be false in ValidationResult")
        return False


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validation_result_json_schema() -> dict:
    return ValidationResult.model_json_schema()


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts" / "validation_result.schema.json"


def write_validation_result_schema(path: Optional[Path] = None) -> Path:
    target = path or default_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(validation_result_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ValidationResult JSON Schema.")
    parser.add_argument("--out", default=str(default_schema_path()))
    args = parser.parse_args()
    print(f"Wrote {write_validation_result_schema(Path(args.out))}")


if __name__ == "__main__":
    main()
