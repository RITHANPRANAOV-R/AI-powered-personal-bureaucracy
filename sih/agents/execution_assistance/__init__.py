"""Execution & Assistance Agent package."""

from .agent import ExecutionAgent, ExecutionAgentError, execute_approved_steps
from .schema import (
    CONTRACT_VERSION,
    DEFAULT_ALLOWED_HOSTS,
    DEFAULT_STARTING_URL,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    FieldActionRecord,
    PortalObservation,
    StepExecutionResult,
    StepExecutionStatus,
    UserExecutionApproval,
    UserPausePoint,
)

__all__ = [
    "execute_approved_steps",
    "ExecutionAgent",
    "ExecutionAgentError",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "StepExecutionStatus",
    "UserExecutionApproval",
    "FieldActionRecord",
    "UserPausePoint",
    "PortalObservation",
    "StepExecutionResult",
    "CONTRACT_VERSION",
    "DEFAULT_STARTING_URL",
    "DEFAULT_ALLOWED_HOSTS",
]
