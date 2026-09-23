"""Pydantic contracts for the Information Retrieval Agent.

IntentResult and ProfileContextResult are imported and not redefined.
"""

from __future__ import annotations

import argparse
import json
from enum import Enum
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.intent_understanding.schema import IntentResult, TaskType
from agents.user_context.schema import ProfileContextResult


CONTRACT_VERSION = "1.0"


class RetrievalStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    NO_EVIDENCE = "no_evidence"
    BLOCKED = "blocked"
    FAILED = "failed"


class ProcessingMode(str, Enum):
    DETERMINISTIC = "deterministic"
    OLLAMA = "ollama"
    MIXED = "mixed"


class SourceType(str, Enum):
    OFFICIAL_WEBPAGE = "official_webpage"
    OFFICIAL_PDF = "official_pdf"
    OFFICIAL_DOWNLOAD = "official_download"


class SourceCheckStatus(str, Enum):
    FETCHED = "fetched"
    BLOCKED = "blocked"
    REDIRECT_REJECTED = "redirect_rejected"
    PARSE_FAILED = "parse_failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"


class RequirementSourceStatus(str, Enum):
    OFFICIAL_CURRENT_CHECKED = "official_current_checked"
    OFFICIAL_DATE_UNCLEAR = "official_date_unclear"
    CONFLICTING_OFFICIAL_SOURCES = "conflicting_official_sources"


class OfficialSourceSpec(BaseModel):
    """Configured official start URL. Never taken from user documents."""

    model_config = ConfigDict(extra="ignore")

    source_id: str
    url: str
    title: str = ""
    category: str = "official"


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str = Field(description="Generic official-source query; no personal values")
    basis: str = Field(description="Which intent fields produced this query")


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evidence_id: str
    source_title: str
    source_url: str
    source_host: str
    source_type: SourceType
    retrieved_at: str
    published_or_updated_at: Optional[str] = None
    section_heading: Optional[str] = None
    excerpt: str = Field(description="Bounded verbatim excerpt; not a full page")
    content_hash: Optional[str] = None
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    supports: List[str] = Field(default_factory=list)


class RequirementCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requirement_id: str
    statement: str
    evidence_ids: List[str] = Field(min_length=1)
    jurisdiction_scope: str = "unknown"
    source_status: RequirementSourceStatus = RequirementSourceStatus.OFFICIAL_DATE_UNCLEAR
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SourceCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    title: Optional[str] = None
    host: Optional[str] = None
    status: SourceCheckStatus
    retrieved_at: Optional[str] = None
    http_status: Optional[int] = None
    warning: Optional[str] = None


class InformationRetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    intent: IntentResult
    profile_context: ProfileContextResult
    allowed_source_hosts: List[str] = Field(
        default_factory=list,
        description="Hostname allowlist. Empty means the Passport Seva default allowlist.",
    )
    source_registry: List[OfficialSourceSpec] = Field(default_factory=list)
    max_sources: int = Field(default=6, ge=1, le=20)
    use_semantic_search: bool = True
    language: Optional[str] = None

    @model_validator(mode="after")
    def _ids_should_align(self) -> "InformationRetrievalRequest":
        # Mismatch is flagged by the agent; keep the objects typed here.
        return self


class RetrievedEvidenceResult(BaseModel):
    """Canonical handoff to Workflow Planning together with intent and profile context."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default=CONTRACT_VERSION)
    request_id: str
    intent_request_id: str
    profile_context_request_id: str
    service_name: Optional[str] = None
    task_type: TaskType
    jurisdiction: Optional[str] = None
    retrieval_status: RetrievalStatus
    search_queries: List[SearchQuery] = Field(default_factory=list)
    evidence: List[EvidenceRecord] = Field(default_factory=list)
    requirements_found: List[RequirementCandidate] = Field(default_factory=list)
    unanswered_questions: List[str] = Field(default_factory=list)
    sources_checked: List[SourceCheck] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    processing_mode: ProcessingMode = ProcessingMode.DETERMINISTIC

    @model_validator(mode="after")
    def _requirements_must_cite_evidence(self) -> "RetrievedEvidenceResult":
        known = {item.evidence_id for item in self.evidence}
        valid: list[RequirementCandidate] = []
        for req in self.requirements_found:
            cited = [eid for eid in req.evidence_ids if eid in known]
            if cited:
                valid.append(req.model_copy(update={"evidence_ids": cited}))
        object.__setattr__(self, "requirements_found", valid)
        return self


def retrieved_evidence_json_schema() -> dict:
    return RetrievedEvidenceResult.model_json_schema()


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts" / "retrieved_evidence_result.schema.json"


def write_retrieved_evidence_schema(path: Optional[Path] = None) -> Path:
    target = path or default_schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(retrieved_evidence_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RetrievedEvidenceResult JSON Schema.")
    parser.add_argument("--out", default=str(default_schema_path()))
    args = parser.parse_args()
    print(f"Wrote {write_retrieved_evidence_schema(Path(args.out))}")


if __name__ == "__main__":
    main()
