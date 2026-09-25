"""Step Scoping Adapter: constructs narrowed execution plan view for compliance validation.

Compliance agent rules are 100% frozen and unmodified. This adapter filters out user-handled
credential steps (containing secret keywords) and cleans up DAG dependencies before passing
the scoped plan to Compliance and Execution.
"""

from __future__ import annotations

import logging
import re
from typing import List, Set, Tuple

from agents.workflow_planning.schema import PlanStep, WorkflowPlan

logger = logging.getLogger(__name__)

SECRET_KEYWORDS_REGEX = re.compile(
    r"\b(password|otp|captcha|pin|cvv|secret|auth_token|recovery_code|token)\b",
    re.IGNORECASE,
)


def is_secret_step(step: PlanStep) -> bool:
    """Return True if step title, description, step_id, or required_fact_keys reference secret keywords."""
    text_to_check = f"{step.step_id} {step.title} {step.description} {' '.join(step.required_fact_keys)}".lower()
    return bool(SECRET_KEYWORDS_REGEX.search(text_to_check))


def scope_workflow_plan(original_plan: WorkflowPlan) -> Tuple[WorkflowPlan, List[PlanStep]]:
    """
    Construct a narrowed execution plan view for compliance validation.

    - Removes user-handled secret steps (password, CAPTCHA, OTP, etc.).
    - Removes internal profile-confirmation meta-steps if present.
    - Cleans up depends_on references to dropped steps so the plan DAG stays valid.
    - Preserves all genuine action steps and evidence provenance.
    """
    print("[SCOPE] Compliance agent rules are unmodified; narrow execution plan view constructed for compliance validation.")
    
    dropped_steps: List[PlanStep] = []
    kept_steps: List[PlanStep] = []
    dropped_step_ids: Set[str] = set()

    for step in original_plan.steps:
        # 1. Secret / Credential steps -> User Handled
        if is_secret_step(step):
            dropped_steps.append(step)
            dropped_step_ids.add(step.step_id)
            print(f"[SCOPE] dropped={step.step_id} reason=User-handled credential/secret step (never automated)")
            continue

        # 2. Drop meta-steps like confirm-unconfirmed-profile-facts if present in plan
        if step.step_id == "confirm-unconfirmed-profile-facts":
            dropped_steps.append(step)
            dropped_step_ids.add(step.step_id)
            print(f"[SCOPE] dropped={step.step_id} reason=Handled via orchestrator fact consent loop")
            continue

        kept_steps.append(step)

    # Clean up depends_on references to dropped steps in kept steps
    cleaned_kept_steps: List[PlanStep] = []
    for step in kept_steps:
        new_deps = [dep for dep in step.depends_on if dep not in dropped_step_ids]
        if new_deps != step.depends_on:
            step_copy = step.model_copy(update={"depends_on": new_deps})
            cleaned_kept_steps.append(step_copy)
        else:
            cleaned_kept_steps.append(step)

    scoped_plan = original_plan.model_copy(update={"steps": cleaned_kept_steps})
    return scoped_plan, dropped_steps
