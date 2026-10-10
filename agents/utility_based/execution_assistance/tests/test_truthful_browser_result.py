from agents.utility_based.execution_assistance.tests.review_fixtures import enroll, resolve_review, confirm_review, bind_context
import importlib
from unittest.mock import Mock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("state", ["VERIFIED_SUCCESS", "FAILED", "NEEDS_USER", "BLOCKED", "UNKNOWN"])
def test_browser_endpoint_preserves_explicit_outcome(state):
    with patch("agents.orchestration.pipeline.create_production_orchestrator", return_value=Mock()), patch("agents.orchestration.document_input.AadhaarDocumentService", return_value=Mock()):
        api = importlib.import_module("api.app")
    from agents.utility_based.execution_assistance.interactive_session import interactive_manager
    from agents.utility_based.execution_assistance.tests.test_context_boundaries import context
    ctx, headers = bind_context(context())
    payload = {
        "session_id": "fixture", "current_stage": "stage_1b_login", "is_completed": False,
        "execution_result": {"status": state, "message": "Fixture outcome"},
    }
    with patch.object(interactive_manager, "submit_step", new=AsyncMock(return_value=payload)):
        response = TestClient(api.create_app(document_service=Mock())).post("/api/browser/submit-step", json={"request_id": "fixture-attempt", "expected_stage": "stage_1b_login", "expected_state_version": 0, "session_id": ctx.session_id, "user_consent": True}, headers=headers)
    assert response.status_code == 200
    assert response.json() == payload
