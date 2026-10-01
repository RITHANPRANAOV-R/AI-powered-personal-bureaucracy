"""Single source of truth for government allowed-host sets and official source registries."""

from __future__ import annotations

from typing import List
from agents.information_retrieval.schema import OfficialSourceSpec

RETRIEVAL_HOSTS: List[str] = [
    "rtionline.gov.in",
    "www.rtionline.gov.in",
    "uidai.gov.in",
    "myaadhaar.uidai.gov.in",
    "resident.uidai.gov.in",
    "passportindia.gov.in",
    "services2.passportindia.gov.in",
    "www.passportindia.gov.in",
    "consumerhelpline.gov.in",
    "edaakhil.nic.in",
    "voters.eci.gov.in",
    "eci.gov.in",
    "incometax.gov.in",
]

EXECUTION_HOSTS: List[str] = [
    "rtionline.gov.in",
    "www.rtionline.gov.in",
    "uidai.gov.in",
    "myaadhaar.uidai.gov.in",
    "resident.uidai.gov.in",
    "passportindia.gov.in",
    "services2.passportindia.gov.in",
    "www.passportindia.gov.in",
    "consumerhelpline.gov.in",
    "edaakhil.nic.in",
    "voters.eci.gov.in",
    "eci.gov.in",
    "incometax.gov.in",
]

# Union of retrieval and execution hosts
UNION_HOSTS: List[str] = list(sorted(set(RETRIEVAL_HOSTS + EXECUTION_HOSTS)))

# Registry of official source URLs for retrieval across official Indian government services
OFFICIAL_SOURCE_REGISTRY: List[OfficialSourceSpec] = [
    # RTI Online
    OfficialSourceSpec(
        source_id="rti_guidelines",
        url="https://rtionline.gov.in/guidelines.php?request",
        title="RTI Online Guidelines & Request Form",
        category="registration",
    ),
    OfficialSourceSpec(
        source_id="rti_home",
        url="https://rtionline.gov.in/",
        title="RTI Online Portal India",
        category="portal",
    ),
    # UIDAI / Aadhaar
    OfficialSourceSpec(
        source_id="aadhaar_status",
        url="https://myaadhaar.uidai.gov.in/CheckAadhaarStatus",
        title="UIDAI myAadhaar Check Enrolment & Update Status",
        category="tracking",
    ),
    OfficialSourceSpec(
        source_id="aadhaar_portal",
        url="https://myaadhaar.uidai.gov.in/login",
        title="UIDAI myAadhaar Official Services & Update Portal",
        category="registration",
    ),
    OfficialSourceSpec(
        source_id="aadhaar_home",
        url="https://uidai.gov.in/",
        title="Unique Identification Authority of India (UIDAI)",
        category="portal",
    ),
    # Passport Seva
    OfficialSourceSpec(
        source_id="passport_reg",
        url="https://services2.passportindia.gov.in/psp/login",
        title="Passport Seva Login & New User Registration",
        category="registration",
    ),
    OfficialSourceSpec(
        source_id="passport_portal",
        url="https://www.passportindia.gov.in/",
        title="Passport Seva Official Portal",
        category="portal",
    ),
    # National Consumer Helpline
    OfficialSourceSpec(
        source_id="consumer_reg",
        url="https://consumerhelpline.gov.in/user/signup.php",
        title="National Consumer Helpline Citizen Registration & Grievance",
        category="registration",
    ),
    OfficialSourceSpec(
        source_id="consumer_helpline",
        url="https://consumerhelpline.gov.in/",
        title="National Consumer Helpline Portal",
        category="portal",
    ),
    # Voters Service
    OfficialSourceSpec(
        source_id="voters_login",
        url="https://voters.eci.gov.in/login",
        title="Election Commission of India Voter Services Login & Form 6",
        category="registration",
    ),
    OfficialSourceSpec(
        source_id="voters_portal",
        url="https://voters.eci.gov.in/",
        title="Election Commission of India Voters Portal",
        category="portal",
    ),
]


def get_allowed_hosts(purpose: str = "union") -> List[str]:
    """Return host allowlist for a specific purpose."""
    if purpose == "retrieval":
        return list(RETRIEVAL_HOSTS)
    elif purpose == "execution":
        return list(EXECUTION_HOSTS)
    return list(UNION_HOSTS)


def get_official_source_registry() -> List[OfficialSourceSpec]:
    """Return official source registry specs for retrieval."""
    return list(OFFICIAL_SOURCE_REGISTRY)
