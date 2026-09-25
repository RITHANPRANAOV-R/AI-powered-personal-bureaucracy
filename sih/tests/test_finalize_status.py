"""Unit tests for terminal workflow status derivation matrix."""

import unittest

from agents.execution_assistance.schema import ExecutionStatus
from src.bureaucracy_agent.orchestrator.finalize import derive_terminal_status
from src.bureaucracy_agent.orchestrator.state import OrchestratorState
from src.bureaucracy_agent.orchestrator.statuses import WorkflowStatus


class TestFinalizeStatus(unittest.TestCase):
    def test_confirmation_observed_returns_completed(self):
        state = OrchestratorState()
        state.confirmation_observed = True
        self.assertEqual(derive_terminal_status(state), WorkflowStatus.COMPLETED)

    def test_submission_attempted_no_confirmation_returns_uncertain(self):
        state = OrchestratorState()
        state.submission_attempted = True
        state.confirmation_observed = False
        self.assertEqual(derive_terminal_status(state), WorkflowStatus.UNCERTAIN)

    def test_user_declined_at_review_returns_cancelled(self):
        state = OrchestratorState()
        state.execution_result = {
            "contract_version": "1.0",
            "execution_request_id": "exec-1",
            "request_id": state.request_id,
            "plan_id": "plan-1",
            "plan_version": 1,
            "validation_request_id": "val-1",
            "execution_status": "cancelled",
        }
        self.assertEqual(derive_terminal_status(state), WorkflowStatus.CANCELLED)

    def test_compliance_stop_returns_stop_blocked(self):
        state = OrchestratorState()
        state.workflow_status = WorkflowStatus.STOP_BLOCKED
        self.assertEqual(derive_terminal_status(state), WorkflowStatus.STOP_BLOCKED)

    def test_driver_error_returns_failed(self):
        state = OrchestratorState()
        state.execution_result = {
            "contract_version": "1.0",
            "execution_request_id": "exec-1",
            "request_id": state.request_id,
            "plan_id": "plan-1",
            "plan_version": 1,
            "validation_request_id": "val-1",
            "execution_status": "failed",
        }
        self.assertEqual(derive_terminal_status(state), WorkflowStatus.FAILED)

    def test_paused_states_stay_paused(self):
        state = OrchestratorState()
        state.workflow_status = WorkflowStatus.PAUSED_FACT_CONSENT
        self.assertEqual(derive_terminal_status(state), WorkflowStatus.PAUSED_FACT_CONSENT)


if __name__ == "__main__":
    unittest.main()
