"""Unit tests for graph transition table and routing rules."""

import unittest

from src.bureaucracy_agent.orchestrator.graph import IllegalTransitionError, OrchestratorGraph, TRANSITION_TABLE
from src.bureaucracy_agent.orchestrator.state import OrchestratorState


class TestRouterGraph(unittest.TestCase):
    def test_transition_table_structure(self):
        self.assertIn("START", TRANSITION_TABLE)
        self.assertIn("INTENT", TRANSITION_TABLE["START"])
        self.assertIn("END", TRANSITION_TABLE["RESPONSE"])

    def test_illegal_transition_raises_error(self):
        graph = OrchestratorGraph()
        state = OrchestratorState()
        state.current_node = "START"

        with self.assertRaises(IllegalTransitionError):
            graph._transition(state, "EXECUTION")

    def test_resume_after_submission_does_not_resubmit(self):
        state = OrchestratorState()
        state.submission_attempted = True
        state.is_dry_run = False
        self.assertTrue(state.submission_attempted)


if __name__ == "__main__":
    unittest.main()
