"""WorkflowStatus enum for the bureaucracy assistant orchestrator."""

from enum import Enum


class WorkflowStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOP_BLOCKED = "STOP_BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNCERTAIN = "UNCERTAIN"
    PAUSED_NEEDS_INPUT = "PAUSED_NEEDS_INPUT"
    PAUSED_FACT_CONSENT = "PAUSED_FACT_CONSENT"
    PAUSED_NEEDS_AUTHORIZATION = "PAUSED_NEEDS_AUTHORIZATION"
    PAUSED_CAPTCHA = "PAUSED_CAPTCHA"
    PAUSED_PAYMENT = "PAUSED_PAYMENT"

    @property
    def is_paused(self) -> bool:
        return self.value.startswith("PAUSED_")

    @property
    def is_terminal(self) -> bool:
        return self in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.STOP_BLOCKED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.UNCERTAIN,
        }
