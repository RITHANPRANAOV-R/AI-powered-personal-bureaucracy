"""Unit tests for explicit authorization and fact consent handling."""

import unittest

from src.bureaucracy_agent.orchestrator.consent import (
    FORBIDDEN_SUBMISSION_PHRASE,
    REQUIRED_AUTHORIZATION_PHRASE,
    process_user_authorization,
)
from src.bureaucracy_agent.orchestrator.state import OrchestratorState


class TestAuthorizationConsent(unittest.TestCase):
    def test_authorization_phrase_accepted(self):
        state = OrchestratorState()
        state.validation_result = {
            "contract_version": "1.0",
            "validation_request_id": "val-1",
            "request_id": state.request_id,
            "plan_id": "plan-1",
            "plan_version": 1,
            "validation_phase": "pre_execution",
            "decision": "approve",
            "eligible_for_user_review": True,
            "eligible_step_ids": ["step-1"],
            "validated_at": "2026-01-01T00:00:00Z",
            "summary": "Approved",
        }

        ok, comp_apprs, exec_apprs, msg = process_user_authorization(state, REQUIRED_AUTHORIZATION_PHRASE)
        self.assertTrue(ok)
        self.assertGreater(len(comp_apprs), 0)
        self.assertGreater(len(exec_apprs), 0)
        self.assertIsNotNone(state.user_authorizations)

    def test_submission_phrase_rejected_as_authorization(self):
        state = OrchestratorState()
        ok, comp_apprs, exec_apprs, msg = process_user_authorization(state, FORBIDDEN_SUBMISSION_PHRASE)
        self.assertFalse(ok)
        self.assertIn("submission phrase", msg.lower())
        self.assertEqual(len(comp_apprs), 0)

    def test_random_phrase_rejected_as_authorization(self):
        state = OrchestratorState()
        ok, comp_apprs, exec_apprs, msg = process_user_authorization(state, "random text")
        self.assertFalse(ok)
        self.assertIn("invalid authorization phrase", msg.lower())


if __name__ == "__main__":
    unittest.main()
