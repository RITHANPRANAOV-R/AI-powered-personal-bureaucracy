"""Confirmation page extractor: extracts ONLY labelled values actually present."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

CONFIRMATION_PATTERNS = [
    r"(Application Reference Number(?:\s*\(ARN\))?|RTI Registration Number|Registration Number|Diary Number|\bRegistration No\.?|\bARN\b)\s*[:=]\s*([A-Za-z0-9/_@:-]+)",
    r"(File Number|\bFile No\.?)\s*[:=]\s*([A-Za-z0-9/-]+)",
    r"(Public Authority|Ministry/Department|Passport Seva Kendra|PSK|Office)\s*[:=]\s*([A-Za-z0-9\s,.-]+)",
    r"(Filing Date|Date of Receipt|Appointment Date|Date & Time)\s*[:=]\s*([A-Za-z0-9\s,:-]+)",
    r"(Transaction ID|Payment Reference|Receipt No\.?)\s*[:=]\s*([A-Za-z0-9/-]+)",
    r"(Payment Status|Status)\s*[:=]\s*([A-Za-z0-9\s_-]+)",
]

EXPLICIT_CONFIRMATION_MESSAGES = [
    "Your RTI Request has been filed successfully",
    "RTI Request Registration Number",
    "User Registration Completed Successfully",
    "Registration Successful",
    "Thank you for registering",
    "Your application has been submitted successfully",
    "Account activation link has been sent to your email",
]


def extract_confirmation_details(page_text: str) -> Tuple[bool, Optional[str], Dict[str, str]]:
    """
    Extract labelled confirmation references from official page inner text.

    Returns:
        (confirmation_observed: bool, confirmation_reference: str, details_dict: dict)
    """
    extracted: Dict[str, str] = {}

    for pattern in CONFIRMATION_PATTERNS:
        matches = re.findall(pattern, page_text, re.IGNORECASE)
        for label, val in matches:
            label_clean = label.strip()
            val_clean = val.strip()
            if val_clean and label_clean not in extracted:
                extracted[label_clean] = val_clean

    found_msg = None
    for msg in EXPLICIT_CONFIRMATION_MESSAGES:
        if msg.lower() in page_text.lower():
            found_msg = msg
            break

    if not extracted and not found_msg:
        return False, None, {}

    ref_parts = [f"{lbl}: {val}" for lbl, val in extracted.items()]
    if found_msg:
        ref_parts.append(f"Confirmation Message: {found_msg}")

    ref_string = "; ".join(ref_parts)
    return True, ref_string, extracted
