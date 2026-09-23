"""Pre-flight safety gates, credential protection, host allowlisting, and privacy masking.

No generative LLM is used. Safety checks are 100% deterministic Python functions.
"""

from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import urlparse

from agents.compliance_validation.schema import ValidationDecision
from agents.user_context.schema import FactStatus

from .schema import DEFAULT_ALLOWED_HOSTS, ExecutionRequest


SECRET_KEYWORDS = re.compile(
    r"\b(password|pass|otp|captcha|pin|cvv|secret|auth_token|recovery_code|token)\b",
    re.IGNORECASE,
)


class ExecutionPreflightError(ValueError):
    """Raised when pre-flight validation gates fail."""


def validate_execution_request(request: ExecutionRequest) -> List[str]:
    """
    Validate pre-flight compliance, matching request IDs, eligible steps,
    step approvals, and confirmed fact prerequisites before browser launch.
    """
    warnings: List[str] = []

    # 1. Correlation ID check
    intent = request.intent
    profile = request.profile_context
    evidence = request.retrieved_evidence
    plan = request.workflow_plan
    val_res = request.validation_result

    ids = {
        "intent": intent.request_id,
        "profile": profile.intent_request_id,
        "evidence": evidence.intent_request_id,
        "plan": plan.request_id,
        "validation": val_res.request_id,
        "request": request.request_id,
    }
    if len(set(ids.values())) > 1:
        raise ExecutionPreflightError(
            f"Correlation ID mismatch across inputs: {ids}"
        )

    # 2. Validation decision check
    if val_res.decision == ValidationDecision.BLOCK or not val_res.eligible_for_user_review:
        raise ExecutionPreflightError(
            f"Cannot execute: ValidationResult decision is {val_res.decision.value} "
            f"and eligible_for_user_review={val_res.eligible_for_user_review}."
        )

    # 3. Selected steps check
    if not request.selected_step_ids:
        raise ExecutionPreflightError("ExecutionRequest must specify at least one step in selected_step_ids.")

    ineligible = set(request.selected_step_ids) - set(val_res.eligible_step_ids)
    if ineligible:
        raise ExecutionPreflightError(
            f"Selected steps {sorted(ineligible)} are not in validation eligible_step_ids {val_res.eligible_step_ids}."
        )

    # 4. User approval check for selected steps
    approved_step_ids = {
        appr.step_id for appr in request.user_approvals if appr.approved_by_user
    }
    unapproved_selected = set(request.selected_step_ids) - approved_step_ids
    if unapproved_selected:
        raise ExecutionPreflightError(
            f"Selected steps {sorted(unapproved_selected)} lack explicit user execution approval records."
        )

    # 5. Confirmed facts prerequisite check
    for fact in request.confirmed_facts:
        if fact.status != FactStatus.USER_CONFIRMED or not fact.confirmed_by_user:
            raise ExecutionPreflightError(
                f"Fact '{fact.key}' supplied in confirmed_facts is not user_confirmed."
            )

    # 6. Reject prior submission_attempted / uncertain states without fresh manual authorization
    if val_res.decision == ValidationDecision.NEEDS_USER_INPUT:
        warnings.append(
            "Validation result flagged needs_user_input; executing only approved non-consequential or pre-reviewed steps."
        )

    return warnings


def check_host_allowlist(url: str, allowed_hosts: List[str] = None) -> bool:
    """Check if the target URL host belongs to the allowlisted domains."""
    hosts = allowed_hosts or DEFAULT_ALLOWED_HOSTS
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        return any(
            hostname == h.lower() or hostname.endswith("." + h.lower())
            for h in hosts
        )
    except Exception:
        return False


def is_secret_field(field_name_or_label: str) -> bool:
    """Return True if field is an authentication secret, password, OTP, or CAPTCHA."""
    return bool(SECRET_KEYWORDS.search(field_name_or_label))


def mask_sensitive_value(key: str, value: str) -> str:
    """
    Redact or mask sensitive personal information for display in terminal logs.
    """
    if not value or not str(value).strip():
        return "[EMPTY]"
    val_str = str(value).strip()
    key_lower = key.lower()

    if is_secret_field(key_lower):
        return "********"
    if "email" in key_lower:
        parts = val_str.split("@", 1)
        if len(parts) == 2:
            name, domain = parts
            masked_name = name[0] + "***" if len(name) > 1 else "*"
            return f"{masked_name}@{domain}"
        return "***@***"
    if any(k in key_lower for k in ("phone", "mobile", "dob", "birth", "number", "aadhaar", "pan")):
        if len(val_str) <= 4:
            return "****"
        return val_str[:2] + "*" * (len(val_str) - 4) + val_str[-2:]
    if len(val_str) > 4:
        return val_str[0] + "*" * (len(val_str) - 2) + val_str[-1]
    return val_str[0] + "***"
