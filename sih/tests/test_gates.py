"""Unit tests for readiness_gate and pre_execution_gate."""

import unittest

from agents.compliance_validation.schema import ValidationDecision, ValidationResult
from agents.information_retrieval.schema import EvidenceRecord, RetrievedEvidenceResult, RetrievalStatus
from src.bureaucracy_agent.orchestrator.gates import pre_execution_gate, readiness_gate
from src.bureaucracy_agent.orchestrator.state import OrchestratorState


class TestGates(unittest.TestCase):
    def test_readiness_gate_fails_when_retrieval_blocked(self):
        state = OrchestratorState()
        state.evidence_result = {
            "contract_version": "1.0",
            "request_id": state.request_id,
            "intent_request_id": state.request_id,
            "profile_context_request_id": state.request_id,
            "task_type": "register",
            "retrieval_status": "blocked",
            "evidence": [],
            "requirements_found": [],
        }
        state.validation_result = {
            "contract_version": "1.0",
            "validation_request_id": "val-1",
            "request_id": state.request_id,
            "plan_id": "plan-1",
            "plan_version": 1,
            "validation_phase": "pre_execution",
            "decision": "approve",
            "eligible_for_user_review": True,
            "validated_at": "2026-01-01T00:00:00Z",
            "summary": "Eligible",
        }

        ok, reasons = readiness_gate(state)
        self.assertFalse(ok)
        self.assertTrue(any("blocked" in r.lower() for r in reasons))

    def test_readiness_gate_fails_when_compliance_blocks(self):
        state = OrchestratorState()
        state.evidence_result = {
            "contract_version": "1.0",
            "request_id": state.request_id,
            "intent_request_id": state.request_id,
            "profile_context_request_id": state.request_id,
            "task_type": "register",
            "retrieval_status": "completed",
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "source_title": "Official Portal",
                    "source_url": "https://rtionline.gov.in/guidelines.php?request",
                    "source_host": "rtionline.gov.in",
                    "source_type": "official_webpage",
                    "retrieved_at": "2026-01-01T00:00:00Z",
                    "excerpt": "Official RTI request submission procedure.",
                }
            ],
            "requirements_found": [
                {
                    "requirement_id": "req-1",
                    "statement": "Registration is mandatory for online submission.",
                    "evidence_ids": ["ev-1"],
                }
            ],
        }
        state.validation_result = {
            "contract_version": "1.0",
            "validation_request_id": "val-1",
            "request_id": state.request_id,
            "plan_id": "plan-1",
            "plan_version": 1,
            "validation_phase": "pre_execution",
            "decision": "block",
            "eligible_for_user_review": False,
            "validated_at": "2026-01-01T00:00:00Z",
            "summary": "Blocked by policy",
        }

        ok, reasons = readiness_gate(state)
        self.assertFalse(ok)
        self.assertTrue(any("block" in r.lower() for r in reasons))

    def test_pre_execution_gate_refuses_when_authorization_missing(self):
        state = OrchestratorState()
        state.evidence_result = {
            "contract_version": "1.0",
            "request_id": state.request_id,
            "intent_request_id": state.request_id,
            "profile_context_request_id": state.request_id,
            "task_type": "register",
            "retrieval_status": "completed",
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "source_title": "Official Portal",
                    "source_url": "https://rtionline.gov.in/guidelines.php?request",
                    "source_host": "rtionline.gov.in",
                    "source_type": "official_webpage",
                    "retrieved_at": "2026-01-01T00:00:00Z",
                    "excerpt": "Official RTI request instructions.",
                }
            ],
            "requirements_found": [
                {
                    "requirement_id": "req-1",
                    "statement": "Registration is mandatory.",
                    "evidence_ids": ["ev-1"],
                }
            ],
        }
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
        state.user_authorizations = []  # No authorization!

        ok, reasons = pre_execution_gate(state)
        self.assertFalse(ok)
        self.assertTrue(any("authorizations" in r.lower() for r in reasons))


if __name__ == "__main__":
    unittest.main()
