"""Authorization and User Consent manager for Orchestrator state safety gates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Set

from src.bureaucracy_agent.orchestrator.state import OneRunAuthorization


UPFRONT_AUTHORIZATION_PHRASE = "AUTHORIZE PASSPORT SEVA REGISTRATION AND SUBMISSION"
SUBMIT_APPROVAL_PHRASE = "SUBMIT PASSPORT SEVA REGISTRATION"

VALID_UPFRONT_PHRASES: Set[str] = {
    UPFRONT_AUTHORIZATION_PHRASE.upper(),
    SUBMIT_APPROVAL_PHRASE.upper(),
}


def validate_upfront_phrase(input_phrase: str) -> bool:
    """Validate user input against required upfront authorization phrases."""
    if not input_phrase:
        return False
    return input_phrase.strip().upper() in VALID_UPFRONT_PHRASES


def create_one_run_authorization(input_phrase: str) -> OneRunAuthorization:
    """Create a OneRunAuthorization object if phrase matches."""
    is_valid = validate_upfront_phrase(input_phrase)
    return OneRunAuthorization(
        phrase=input_phrase.strip(),
        scope="PASSPORT SEVA REGISTRATION AND SUBMISSION",
        authorized=is_valid,
        authorized_at=datetime.now(timezone.utc).isoformat() if is_valid else None,
    )
