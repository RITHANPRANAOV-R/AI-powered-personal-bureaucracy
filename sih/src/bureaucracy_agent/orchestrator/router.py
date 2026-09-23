"""Deterministic router functions for Orchestrator workflow graph transitions."""

from __future__ import annotations

from typing import Dict, Any
from src.bureaucracy_agent.orchestrator.state import OrchestratorState


def route_after_intent_understanding(state: OrchestratorState) -> str:
    """Route after Intent Understanding Agent node."""
    res = state.intent_result or {}
    status = str(res.get("status", "")).lower()
    if status == "needs_clarification" or res.get("clarification_questions"):
        return "NEEDS_USER_INPUT"
    return "USER_CONTEXT"


def route_after_user_context(state: OrchestratorState) -> str:
    """Route after User Context & Profile Agent node."""
    return "INFORMATION_RETRIEVAL"


def route_after_information_retrieval(state: OrchestratorState) -> str:
    """Route after Information Retrieval Agent node."""
    return "WORKFLOW_PLANNING"


def route_after_workflow_planning(state: OrchestratorState) -> str:
    """Route after Workflow Planning Agent node."""
    return "COMPLIANCE_VALIDATION_PRE"


def route_after_compliance_validation_pre(state: OrchestratorState) -> str:
    """Route after pre-execution Compliance & Validation Agent node."""
    res = state.validation_result or {}
    decision = str(res.get("decision", res.get("overall_decision", ""))).lower()

    if decision == "block":
        return "STOP_BLOCKED"
    if decision == "needs_user_input":
        return "NEEDS_USER_INPUT"

    # Check upfront authorization phrase
    auth = state.one_run_authorization
    if not auth or not auth.authorized:
        return "AUTHORIZATION_REQUIRED"

    return "EXECUTION_ASSISTANCE"


def route_after_execution_assistance(state: OrchestratorState) -> str:
    """Route after Execution & Assistance Agent node."""
    res = state.execution_result or {}
    status = str(res.get("status", "")).lower()
    captcha = res.get("captcha_detected", False)

    if captcha or status == "paused_for_user":
        return "PAUSED_CAPTCHA"
    if status in ("failed", "error"):
        return "RESPONSE_GENERATION"
    return "COMPLIANCE_VALIDATION_POST"


def route_after_compliance_validation_post(state: OrchestratorState) -> str:
    """Route after post-execution Compliance & Validation Agent node."""
    return "MONITORING_UPDATE"


def route_after_monitoring_update(state: OrchestratorState) -> str:
    """Route after Monitoring & Update Agent node."""
    return "RESPONSE_GENERATION"
