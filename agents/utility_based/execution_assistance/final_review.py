"""Server-owned final-review approval; no browser or government execution."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import copy
import hashlib
import json

UNKNOWN = "UNKNOWN"


class ReviewState(str, Enum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_READY = "REVIEW_READY"
    APPROVED = "APPROVED"
    APPROVAL_INVALIDATED = "APPROVAL_INVALIDATED"


def binding(package):
    return hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def unknown(value):
    if value is None or value == "" or value == UNKNOWN or value == [] or value == {}:
        return True
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return False


def submission_package(session):
    # Authentication secrets and UI/session timestamps are not submitted demographic data.
    facts = {k: v.model_dump(mode="json") for k, v in session.context.facts.items()
             if "otp" not in k.casefold()}
    def value(key):
        fact = facts.get(key)
        return fact["value"] if fact and fact["value"] not in (None, "") else UNKNOWN
    upload = session.supporting_document_result
    upload_evidence = upload.model_dump(mode="json") if upload is not None else UNKNOWN
    return {
        "service": "Aadhaar Address Update",
        "citizen_information": facts or UNKNOWN,
        "extracted_document_information": value("document_evidence"),
        "corrected_information": {k: v for k, v in facts.items() if v["provenance"] == "user_corrected"} or UNKNOWN,
        "current_values": {k: v for k, v in facts.items() if k.startswith("existing_")} or UNKNOWN,
        "new_values": {k: v for k, v in facts.items() if k.startswith("new_") or k == "pincode"} or UNKNOWN,
        "address": value("new_address") if value("new_address") != UNKNOWN else value("address"),
        "pincode": value("pincode"),
        "supporting_documents": list(session.context.document_refs) or UNKNOWN,
        "document_type": value("document_type"),
        "requirements": value("requirements"),
        "fees": value("fees"),
        "declarations": value("declarations"),
        "upload_validation": upload_evidence,
        "submission_validation": copy.deepcopy(session.submission_validation) if session.submission_validation is not None else UNKNOWN,
        "warnings": value("warnings"),
    }


def blocking_reasons(package):
    reasons = []
    for key in ("service", "address", "pincode", "supporting_documents", "document_type", "requirements", "fees", "declarations"):
        if unknown(package.get(key)):
            reasons.append(f"Required {key} is UNKNOWN or incomplete.")
    facts = package.get("citizen_information", {})
    if isinstance(facts, dict):
        for key, fact in facts.items():
            if isinstance(fact, dict) and fact.get("allowed_for_execution") is True and (fact.get("status") != "confirmed" or unknown(fact.get("value"))):
                reasons.append(f"Submission field {key} is UNKNOWN or not confirmed.")
        for key in ("new_address", "address", "pincode", "document_type", "requirements", "fees", "declarations"):
            fact = facts.get(key)
            if fact and (fact.get("status") != "confirmed" or fact.get("allowed_for_execution") is not True):
                reasons.append(f"Required {key} is not confirmed for execution.")
    requirements = package.get("requirements")
    if not isinstance(requirements, list) or not requirements or any(not isinstance(req, dict) or req.get("grounding_status") != "verified_grounded" or not req.get("evidence_ids") or not req.get("source_url") for req in requirements):
        reasons.append("Applicable requirements are not authoritatively grounded.")
    declarations = package.get("declarations")
    if not isinstance(declarations, list) or not declarations or any(not isinstance(item, dict) or item.get("agreed") is not True or not isinstance(item.get("statement"), str) or not item["statement"].strip() for item in declarations):
        reasons.append("Required declarations have not been explicitly agreed.")
    for key in ("upload_validation", "submission_validation"):
        check = package.get(key)
        if (not isinstance(check, dict) or check.get("status") != "VERIFIED_SUCCESS"
                or not isinstance(check.get("verification_evidence"), str) or not check["verification_evidence"].strip()):
            reasons.append(f"Required {key} is UNKNOWN, failed or unverified.")
    return reasons


@dataclass
class FinalReviewGate:
    state: ReviewState = ReviewState.REVIEW_REQUIRED
    package: dict | None = None
    reviewed_binding: str | None = None
    approved_binding: str | None = None
    approved_at: datetime | None = None
    expires_at: datetime | None = None

    def invalidate(self):
        self.state = ReviewState.APPROVAL_INVALIDATED
        self.approved_binding = None
        self.approved_at = self.expires_at = None

    def view(self, package):
        current = binding(package)
        changed = self.reviewed_binding is not None and current != self.reviewed_binding
        if changed:
            self.invalidate()
        self.package = copy.deepcopy(package)
        self.reviewed_binding = current
        if not changed and self.state != ReviewState.APPROVED:
            self.state = ReviewState.REVIEW_REQUIRED if blocking_reasons(package) else ReviewState.REVIEW_READY
        return self.as_dict()

    def approve(self, package, reviewed_binding, action, now=None):
        if action != "Approve & Submit":
            return "A distinct Approve & Submit action is required."
        if self.package is None:
            return "Final review is required."
        if self.reviewed_binding != binding(package) or reviewed_binding != self.reviewed_binding:
            self.invalidate()
            return "Submission information changed; review and approve again."
        if self.state != ReviewState.REVIEW_READY:
            return "Final review is not ready for approval."
        reasons = blocking_reasons(package)
        if reasons:
            return "; ".join(reasons)
        now = now or datetime.now(timezone.utc)
        self.state = ReviewState.APPROVED
        self.approved_binding = self.reviewed_binding
        self.approved_at = now
        self.expires_at = now + timedelta(minutes=15)  # Local approval policy, not a government rule.
        return None

    def validate(self, package, now=None):
        if self.package is None:
            return "Final review is required before submission."
        if self.reviewed_binding != binding(package):
            self.invalidate()
            return "Submission information changed; final approval is invalidated."
        if self.state == ReviewState.APPROVED and self.approved_binding != binding(package):
            self.invalidate()
        if self.state != ReviewState.APPROVED:
            return "Explicit final approval is required."
        if self.expires_at is None or (now or datetime.now(timezone.utc)) >= self.expires_at:
            self.invalidate()
            return "Final approval expired; review and approve again."
        reasons = blocking_reasons(package)
        if reasons:
            self.invalidate()
            return "; ".join(reasons)
        return None

    def as_dict(self):
        package = copy.deepcopy(self.package)
        return {"state": self.state.value, "package": package,
                "binding": self.reviewed_binding, "approved_binding": self.approved_binding,
                "approved_at": self.approved_at.isoformat() if self.approved_at else None,
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
                "blocking_reasons": blocking_reasons(package) if package is not None else ["Final review is required."],
                "unknown_fields": [k for k, v in (package or {}).items() if unknown(v)]}
