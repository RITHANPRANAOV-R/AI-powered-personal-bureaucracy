from __future__ import annotations

from typing import Final

INTENT_TYPES: Final[tuple[str, ...]] = (
    "status_inquiry",
    "update_request",
    "correction_request",
    "document_request",
    "complaint",
    "enrollment",
    "general_assistance",
)

UPDATE_TARGETS: Final[tuple[str, ...]] = (
    "address",
    "mobile_number",
    "email",
    "name",
    "date_of_birth",
    "gender",
    "biometric",
    "unknown",
)

ENTITY_TYPES: Final[tuple[str, ...]] = (
    "aadhaar_number",
    "address",
    "mobile_number",
    "email",
    "name",
    "date_of_birth",
    "gender",
    "document_type",
    "issue_category",
    "location",
    "reference_date",
)

MISSING_FIELD_MAP: Final[dict[str, str]] = {
    "address": "new_address",
    "mobile_number": "new_mobile_number",
    "email": "new_email",
    "name": "new_name",
    "date_of_birth": "new_date_of_birth",
    "gender": "new_gender",
    "biometric": "new_biometric",
}

INTENT_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "status_inquiry": (
        "status",
        "check status",
        "check my status",
        "track status",
        "what is the status",
        "update status",
    ),
    "update_request": (
        "update",
        "change",
        "modify",
    ),
    "correction_request": (
        "correct",
        "correction",
        "fix",
        "amend",
        "edit",
    ),
    "document_request": (
        "document",
        "certificate",
        "copy",
        "form",
        "e-aadhaar",
        "aadhaar card",
    ),
    "complaint": (
        "problem",
        "issue",
        "complaint",
        "grievance",
        "error",
    ),
    "enrollment": (
        "enroll",
        "enrol",
        "registration",
        "new aadhaar",
    ),
    "general_assistance": (
        "help",
        "assistance",
        "support",
    ),
}

UPDATE_TARGET_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "address": ("address", "residential address", "home address"),
    "mobile_number": ("mobile number", "mobile", "phone number", "phone"),
    "email": ("email", "e-mail"),
    "name": ("name",),
    "date_of_birth": ("date of birth", "dob", "birth date"),
    "gender": ("gender",),
    "biometric": ("biometric", "fingerprint", "iris"),
}
