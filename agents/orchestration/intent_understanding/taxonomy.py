from enum import Enum


class IntentType(str, Enum):
    ENROLLMENT = "enrollment"
    UPDATE = "update"
    CORRECTION = "correction"
    STATUS_INQUIRY = "status_inquiry"
    DOCUMENT_REQUEST = "document_request"
    COMPLAINT = "complaint"
    GENERAL_ASSISTANCE = "general_assistance"


class UpdateType(str, Enum):
    ADDRESS = "address"
    MOBILE_NUMBER = "mobile_number"
    EMAIL = "email"
    NAME = "name"
    DATE_OF_BIRTH = "date_of_birth"
    GENDER = "gender"
    BIOMETRIC = "biometric"
    UNKNOWN = "unknown"


class EntityType(str, Enum):
    AADHAAR_NUMBER = "aadhaar_number"
    ADDRESS = "address"
    MOBILE_NUMBER = "mobile_number"
    EMAIL = "email"
    NAME = "name"
    DATE_OF_BIRTH = "date_of_birth"
    GENDER = "gender"
    DOCUMENT = "document"
    LOCATION = "location"
    REFERENCE_DATE = "reference_date"
    ISSUE_CATEGORY = "issue_category"


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


INTENT_KEYWORDS = {
    IntentType.ENROLLMENT: ["enroll", "enrol", "registration", "new aadhaar"],
    IntentType.UPDATE: ["update", "change", "modify", "correct"],
    IntentType.CORRECTION: ["correction", "fix", "edit"],
    IntentType.STATUS_INQUIRY: ["status", "check status", "track status", "update status"],
    IntentType.DOCUMENT_REQUEST: ["document", "certificate", "copy", "form"],
    IntentType.COMPLAINT: ["complaint", "problem", "issue", "grievance"],
    IntentType.GENERAL_ASSISTANCE: ["help", "assistance", "support"],
}


UPDATE_KEYWORDS = {
    UpdateType.ADDRESS: ["address", "residence", "current address"],
    UpdateType.MOBILE_NUMBER: ["mobile", "phone number", "mobile number"],
    UpdateType.EMAIL: ["email", "e-mail"],
    UpdateType.NAME: ["name"],
    UpdateType.DATE_OF_BIRTH: ["date of birth", "dob", "birth date"],
    UpdateType.GENDER: ["gender"],
    UpdateType.BIOMETRIC: ["biometric", "fingerprint", "iris"],
}


ENTITY_KEYWORDS = {
    EntityType.AADHAAR_NUMBER: ["aadhaar number", "uidai", "aadhaar"],
    EntityType.ADDRESS: ["address"],
    EntityType.MOBILE_NUMBER: ["mobile number", "mobile", "phone number"],
    EntityType.EMAIL: ["email", "e-mail"],
    EntityType.NAME: ["name"],
    EntityType.DATE_OF_BIRTH: ["date of birth", "dob"],
    EntityType.GENDER: ["gender"],
    EntityType.DOCUMENT: ["document", "certificate", "copy"],
    EntityType.LOCATION: ["coimbatore", "chennai", "mumbai", "delhi", "bangalore", "hyderabad"],
    EntityType.REFERENCE_DATE: ["today", "tomorrow", "yesterday", "this week", "next week"],
    EntityType.ISSUE_CATEGORY: ["issue", "problem", "complaint"],
}


URGENCY_KEYWORDS = ["urgent", "immediately", "asap", "emergency"]


def get_priority_value(value: str) -> str:
    return value.lower().strip()
