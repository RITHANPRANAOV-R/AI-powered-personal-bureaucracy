from __future__ import annotations

from abc import ABC, abstractmethod

from agents.orchestration.workflow_planning.schema import PlanStep

from .schema import AdapterResult, ConfirmedExecutionContext


class ExecutionAdapter(ABC):
    """Boundary for an already-authorized service operation."""

    @abstractmethod
    def execute_step(self, step: PlanStep, context: ConfirmedExecutionContext) -> AdapterResult:
        raise NotImplementedError


class MockExecutionAdapter(ExecutionAdapter):
    """Deterministic, offline adapter for execution-core tests."""

    def __init__(self, outcomes: dict[str, AdapterResult] | None = None):
        self.outcomes = dict(outcomes or {})
        self.calls: list[str] = []

    def execute_step(self, step: PlanStep, context: ConfirmedExecutionContext) -> AdapterResult:
        self.calls.append(step.step_id)
        return self.outcomes.get(
            step.step_id,
            AdapterResult(status="completed", outcome=f"Simulated completion of {step.step_id}."),
        )