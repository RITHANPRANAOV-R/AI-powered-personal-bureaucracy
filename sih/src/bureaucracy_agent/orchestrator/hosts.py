"""Single source of truth for RTI Online allowed-host sets and official source registries."""

from __future__ import annotations

from typing import List
from agents.information_retrieval.schema import OfficialSourceSpec

RETRIEVAL_HOSTS: List[str] = [
    "rtionline.gov.in",
    "www.rtionline.gov.in",
]

EXECUTION_HOSTS: List[str] = [
    "rtionline.gov.in",
    "www.rtionline.gov.in",
]

# Union of retrieval and execution hosts
UNION_HOSTS: List[str] = list(sorted(set(RETRIEVAL_HOSTS + EXECUTION_HOSTS)))

# Registry of official source URLs for retrieval
OFFICIAL_SOURCE_REGISTRY: List[OfficialSourceSpec] = [
    OfficialSourceSpec(
        source_id="rti_home",
        url="https://rtionline.gov.in/",
        title="RTI Online Portal India",
        category="portal",
    ),
    OfficialSourceSpec(
        source_id="rti_guidelines",
        url="https://rtionline.gov.in/guidelines.php?request",
        title="RTI Online Guidelines and Request Access",
        category="procedure",
    ),
    OfficialSourceSpec(
        source_id="rti_submit",
        url="https://rtionline.gov.in/request/request.php",
        title="RTI Online Submit Request Form",
        category="registration",
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
