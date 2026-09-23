"""Execution & Assistance Agent implementation.

Guarded Playwright browser automation for Indian Passport Seva registration.
Performs visible form field preparation, manual pause points for credentials/CAPTCHAs,
and exact terminal phrase authorization before submission.

Zero generative LLM calls are made in this agent.
"""

from __future__ import annotations

from pydantic import ValidationError

from .browser import PassportSevaBrowserAutomation
from .safety import ExecutionPreflightError, validate_execution_request
from .schema import ExecutionRequest, ExecutionResult


class ExecutionAgentError(ValueError):
    """Raised when an execution request cannot be parsed or fails pre-flight safety gates."""


class ExecutionAgent:
    """Public Execution & Assistance Agent."""

    def execute_approved_steps(self, request: ExecutionRequest, interactive: bool = True) -> ExecutionResult:
        """
        Public callable for executing validated and user-approved workflow steps.

        Signature:
            def execute_approved_steps(request: ExecutionRequest) -> ExecutionResult
        """
        try:
            request = ExecutionRequest.model_validate(request)
        except ValidationError as exc:
            raise ExecutionAgentError(f"Invalid ExecutionRequest contract: {exc}") from exc

        # Pre-flight safety gates
        try:
            warnings = validate_execution_request(request)
        except ExecutionPreflightError as exc:
            raise ExecutionAgentError(f"Pre-flight safety gate failed: {exc}") from exc

        browser_manager = PassportSevaBrowserAutomation(request, interactive=interactive)
        result = browser_manager.execute_flow()

        if warnings:
            result.warnings.extend(warnings)

        return result


def execute_approved_steps(request: ExecutionRequest, interactive: bool = True) -> ExecutionResult:
    """Public callable interface for Execution & Assistance Agent."""
    return ExecutionAgent().execute_approved_steps(request, interactive=interactive)
