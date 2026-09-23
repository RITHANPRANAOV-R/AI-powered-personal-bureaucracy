"""Information Retrieval Agent: allowlisted official sources only."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import ValidationError

from agents.intent_understanding.schema import IntentResult
from agents.user_context.schema import FactStatus, ProfileContextResult, Sensitivity

from .config import RetrievalConfig, load_retrieval_config
from .index import LocalChunkIndex
from .llm import RetrievalModelUnavailable, RetrievalOllama
from .schema import (
    CONTRACT_VERSION,
    EvidenceRecord,
    InformationRetrievalRequest,
    ProcessingMode,
    RequirementCandidate,
    RequirementSourceStatus,
    RetrievedEvidenceResult,
    RetrievalStatus,
    SearchQuery,
    SourceCheckStatus,
)
from .sources import (
    OfficialFetcher,
    bounded_excerpt,
    chunk_document,
    resolve_hosts,
    resolve_registry,
)

SENSITIVE_PROFILE_KEYS = {
    "full_name",
    "given_name",
    "surname",
    "date_of_birth",
    "email",
    "mobile",
    "present_address",
    "permanent_address",
    "aadhaar_number",
    "passport_number",
    "existing_passport_number",
    "father_name",
    "mother_name",
}

REQUIREMENT_HINTS = (
    "register",
    "registration",
    "mandatory",
    "required",
    "must",
    "document",
    "original",
    "self-attested",
    "appointment",
    "login",
    "user id",
    "e-mail",
    "email id",
    "proof of",
    "fresh passport",
    "psk",
    "photocop",
)


class InformationRetrievalAgent:
    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        *,
        allow_llm: bool = True,
    ) -> None:
        self.config = config or load_retrieval_config()
        self.allow_llm = allow_llm and self.config.allow_llm_extraction
        self.ollama = RetrievalOllama(self.config)

    def retrieve_information(self, request: InformationRetrievalRequest) -> RetrievedEvidenceResult:
        """
        Public callable.

        Signature:
            def retrieve_information(request: InformationRetrievalRequest) -> RetrievedEvidenceResult
        """
        request = InformationRetrievalRequest.model_validate(request)
        warnings: list[str] = []
        used_embed = False
        used_llm = False

        if request.intent.request_id != request.profile_context.intent_request_id:
            warnings.append(
                "intent.request_id does not match profile_context.intent_request_id; retrieval was not run."
            )
            return _empty_result(request, RetrievalStatus.FAILED, warnings, ProcessingMode.DETERMINISTIC)

        service_blob = f"{request.intent.service_name or ''} {request.intent.document_type or ''}".lower()
        if "passport" not in service_blob:
            warnings.append(
                "Configured official registry is Passport Seva / MEA. Other services are not retrieved in this version."
            )

        queries = build_search_queries(request.intent, request.profile_context)
        hosts = resolve_hosts(request.allowed_source_hosts)
        registry = resolve_registry(request.source_registry)
        fetcher = OfficialFetcher(self.config, hosts)
        max_sources = min(request.max_sources, self.config.max_sources)

        documents = []
        checks = []
        seen_urls: set[str] = set()
        queue = [(spec.url, spec.title) for spec in registry]
        while queue and len(documents) < max_sources:
            url, title = queue.pop(0)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            doc, check = fetcher.fetch(url, title)
            checks.append(check)
            if check.warning:
                warnings.append(f"{check.url}: {check.warning}")
            if not doc:
                continue
            if "error.htm" in doc.final_url.lower() or (doc.title or "").lower() in {"error", "page not found"}:
                check = doc.check.model_copy(
                    update={
                        "status": SourceCheckStatus.PARSE_FAILED,
                        "warning": "Official host returned an error page; not used as evidence.",
                    }
                )
                checks[-1] = check
                warnings.append(f"{doc.final_url}: error page ignored.")
                continue
            documents.append(doc)
            for discovered in fetcher.discover_links(doc):
                if discovered not in seen_urls and len(documents) + len(queue) < max_sources:
                    queue.append((discovered, ""))

        if not documents:
            blocked = any(c.status == SourceCheckStatus.BLOCKED for c in checks)
            status = RetrievalStatus.BLOCKED if blocked else RetrievalStatus.FAILED
            if not checks:
                status = RetrievalStatus.NO_EVIDENCE
            return RetrievedEvidenceResult(
                contract_version=CONTRACT_VERSION,
                request_id=request.request_id,
                intent_request_id=request.intent.request_id,
                profile_context_request_id=request.profile_context.request_id,
                service_name=request.intent.service_name,
                task_type=request.intent.task_type,
                jurisdiction=request.intent.jurisdiction,
                retrieval_status=status,
                search_queries=queries,
                sources_checked=checks,
                unanswered_questions=_unanswered(request, []),
                warnings=warnings or ["No official sources could be retrieved."],
                processing_mode=ProcessingMode.DETERMINISTIC,
            )

        index = LocalChunkIndex(self.config)
        index.load()
        chunk_rows: list[dict] = []
        for doc in documents:
            for i, chunk in enumerate(chunk_document(doc)):
                row = {
                    "chunk_id": f"{doc.content_hash[:10]}-{i}",
                    "url": doc.final_url,
                    "host": doc.host,
                    "title": doc.title,
                    "heading": chunk["heading"],
                    "text": chunk["text"],
                    "source_type": doc.source_type.value,
                    "retrieved_at": doc.retrieved_at,
                    "published_or_updated_at": doc.published_or_updated_at,
                    "content_hash": doc.content_hash,
                }
                chunk_rows.append(row)
                index.add_chunk(row)
        index.persist()

        query_text = " ".join(q.query for q in queries)
        query_embedding = None
        if request.use_semantic_search:
            try:
                embeddings = self.ollama.embed([query_text] + [row["text"][:1500] for row in chunk_rows[:24]])
                query_embedding = embeddings[0]
                for row, vector in zip(chunk_rows[:24], embeddings[1:]):
                    row["embedding"] = vector
                used_embed = True
            except (RetrievalModelUnavailable, ValueError, IndexError) as exc:
                warnings.append(f"Semantic matching skipped: {exc}. Keyword matching was used.")

        ranked: list[dict] = []
        seen_chunks: set[str] = set()
        for query in queries:
            q_embed = None
            if used_embed and query_embedding is not None:
                q_embed = query_embedding
            hits = LocalChunkIndex(self.config)
            hits._rows = chunk_rows
            for hit in hits.search(query.query, q_embed, limit=5):
                if hit["chunk_id"] in seen_chunks:
                    continue
                seen_chunks.add(hit["chunk_id"])
                ranked.append(hit)
        if not ranked:
            ranked = chunk_rows[:8]
            for row in ranked:
                row["score"] = 0.2

        evidence: list[EvidenceRecord] = []
        for i, row in enumerate(ranked[:12], start=1):
            evidence.append(
                EvidenceRecord(
                    evidence_id=f"ev-{i:03d}",
                    source_title=row.get("title") or row.get("heading") or "Official source",
                    source_url=row["url"],
                    source_host=row["host"],
                    source_type=row["source_type"],
                    retrieved_at=row["retrieved_at"],
                    published_or_updated_at=row.get("published_or_updated_at"),
                    section_heading=row.get("heading"),
                    excerpt=bounded_excerpt(row.get("text") or ""),
                    content_hash=row.get("content_hash"),
                    relevance_score=float(row.get("score") or 0),
                    supports=[],
                )
            )

        requirements = _deterministic_requirements(evidence, queries)
        questions = _target_questions(request.intent)
        if self.allow_llm and evidence:
            try:
                payload = self.ollama.extract_requirements(
                    [item.model_dump(mode="json") for item in evidence[:8]],
                    questions,
                )
                llm_reqs = _requirements_from_model(payload, evidence)
                if llm_reqs:
                    used_llm = True
                    requirements = _merge_requirements(requirements, llm_reqs)
            except (RetrievalModelUnavailable, ValueError, ValidationError, TypeError) as exc:
                warnings.append(f"LLM evidence extraction skipped: {exc}. Deterministic extraction was used.")

        _link_supports(evidence, requirements)
        unanswered = _unanswered(request, requirements)
        status = _status(documents, checks, evidence, requirements)
        if used_embed or used_llm:
            mode = ProcessingMode.MIXED
        else:
            mode = ProcessingMode.DETERMINISTIC
        if used_llm and used_embed and not documents:
            mode = ProcessingMode.OLLAMA

        dates_unclear = [ev for ev in evidence if not ev.published_or_updated_at]
        if dates_unclear:
            warnings.append(
                "One or more official sources did not expose a clear publication/update date."
            )

        result = RetrievedEvidenceResult(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            intent_request_id=request.intent.request_id,
            profile_context_request_id=request.profile_context.request_id,
            service_name=request.intent.service_name,
            task_type=request.intent.task_type,
            jurisdiction=request.intent.jurisdiction,
            retrieval_status=status,
            search_queries=queries,
            evidence=evidence,
            requirements_found=requirements,
            unanswered_questions=unanswered,
            sources_checked=checks,
            warnings=_dedupe(warnings),
            processing_mode=mode,
        )
        return RetrievedEvidenceResult.model_validate(result.model_dump())


_default_agent = InformationRetrievalAgent()


def retrieve_information(request: InformationRetrievalRequest) -> RetrievedEvidenceResult:
    return _default_agent.retrieve_information(request)


def build_search_queries(intent: IntentResult, profile: ProfileContextResult) -> list[SearchQuery]:
    service = intent.service_name or intent.document_type or "Passport Seva"
    task = intent.task_type.value
    queries = [
        SearchQuery(
            query=f"{service} official {task} procedure",
            basis="intent.service_name and intent.task_type",
        )
    ]
    if task in {"register", "apply"}:
        queries.append(
            SearchQuery(
                query="Passport Seva new user registration official steps",
                basis="intent.task_type register/apply",
            )
        )
        queries.append(
            SearchQuery(
                query="Passport Seva documents required fresh passport official",
                basis="intent.task_type and document_type",
            )
        )
    if task == "renew":
        queries.append(
            SearchQuery(
                query="Passport Seva reissue renewal official documents",
                basis="intent.task_type",
            )
        )
    if intent.jurisdiction:
        queries.append(
            SearchQuery(
                query=f"{service} passport office {intent.jurisdiction} official",
                basis="intent.jurisdiction (not a personal address)",
            )
        )
    # Profile is used only as a generic signal: language already on the request.
    confirmed_keys = [
        fact.key
        for fact in profile.relevant_facts
        if fact.confirmed_by_user
        and fact.status == FactStatus.USER_CONFIRMED
        and fact.sensitivity != Sensitivity.HIGHLY_SENSITIVE
        and fact.key not in SENSITIVE_PROFILE_KEYS
    ]
    if "language_preference" in confirmed_keys:
        queries.append(
            SearchQuery(
                query=f"{service} official guidance",
                basis="confirmed language_preference present; query kept generic",
            )
        )
    return queries[:6]


def _deterministic_requirements(evidence: list[EvidenceRecord], queries: list[SearchQuery]) -> list[RequirementCandidate]:
    found: list[RequirementCandidate] = []
    seen_statements: set[str] = set()
    n = 0
    for ev in evidence:
        sentences = re.split(r"(?<=[.!?])\s+|\n+", ev.excerpt)
        for sentence in sentences:
            text = sentence.strip()
            if len(text) < 40 or len(text) > 280:
                continue
            if text.endswith((" e.g.", " e.g", "(")) or text.count(" ") < 6:
                continue
            if not re.search(r"[.!?]$", text) and len(text) < 80:
                continue
            lowered = text.lower()
            if not any(hint in lowered for hint in REQUIREMENT_HINTS):
                continue
            key = re.sub(r"\s+", " ", lowered)
            if key in seen_statements:
                continue
            seen_statements.add(key)
            n += 1
            status = (
                RequirementSourceStatus.OFFICIAL_CURRENT_CHECKED
                if ev.published_or_updated_at
                else RequirementSourceStatus.OFFICIAL_DATE_UNCLEAR
            )
            found.append(
                RequirementCandidate(
                    requirement_id=f"req-{n:03d}",
                    statement=text,
                    evidence_ids=[ev.evidence_id],
                    jurisdiction_scope="unknown",
                    source_status=status,
                    confidence=round(min(0.7, (ev.relevance_score or 0.3) + 0.2), 3),
                )
            )
            if n >= 10:
                return found
    return found


def _requirements_from_model(payload: dict, evidence: list[EvidenceRecord]) -> list[RequirementCandidate]:
    known = {item.evidence_id: item for item in evidence}
    out: list[RequirementCandidate] = []
    for i, item in enumerate(payload.get("requirements") or [], start=1):
        if not isinstance(item, dict):
            continue
        eid = str(item.get("evidence_id") or "").strip()
        statement = str(item.get("statement") or "").strip()
        if not statement or eid not in known:
            continue
        ev = known[eid]
        status = (
            RequirementSourceStatus.OFFICIAL_CURRENT_CHECKED
            if ev.published_or_updated_at
            else RequirementSourceStatus.OFFICIAL_DATE_UNCLEAR
        )
        try:
            out.append(
                RequirementCandidate(
                    requirement_id=f"req-llm-{i:03d}",
                    statement=statement,
                    evidence_ids=[eid],
                    jurisdiction_scope=str(item.get("jurisdiction_scope") or "unknown"),
                    source_status=status,
                    confidence=item.get("confidence"),
                )
            )
        except ValidationError:
            continue
    return out


def _merge_requirements(
    deterministic: list[RequirementCandidate],
    extra: list[RequirementCandidate],
) -> list[RequirementCandidate]:
    merged = list(deterministic)
    seen = {re.sub(r"\s+", " ", r.statement.lower()) for r in merged}
    for item in extra:
        key = re.sub(r"\s+", " ", item.statement.lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged[:12]


def _link_supports(evidence: list[EvidenceRecord], requirements: list[RequirementCandidate]) -> None:
    by_id = {item.evidence_id: item for item in evidence}
    for req in requirements:
        for eid in req.evidence_ids:
            ev = by_id.get(eid)
            if ev and req.requirement_id not in ev.supports:
                ev.supports.append(req.requirement_id)


def _target_questions(intent: IntentResult) -> list[str]:
    questions = [
        "How does a new user register on the official Passport Seva portal?",
        "What official steps follow registration before a passport application?",
        "Which documents does the official site mention for a fresh passport?",
    ]
    questions.extend(intent.clarification_questions)
    return questions


def _unanswered(request: InformationRetrievalRequest, requirements: list[RequirementCandidate]) -> list[str]:
    blob = " ".join(r.statement.lower() for r in requirements)
    missing: list[str] = []
    if "register" not in blob:
        missing.append("Authoritative registration steps were not clearly extracted from retrieved pages.")
    if "document" not in blob and "proof" not in blob:
        missing.append("Authoritative document list for a fresh passport was not clearly extracted.")
    missing.extend(request.intent.clarification_questions)
    missing.extend(
        f"Requested profile key '{key}' is not a government-rule question and was not used as evidence."
        for key in request.profile_context.missing_requested_facts
    )
    return _dedupe(missing)[:8]


def _status(documents, checks, evidence, requirements) -> RetrievalStatus:
    blocked = any(c.status == SourceCheckStatus.BLOCKED for c in checks)
    failed_count = sum(1 for c in checks if c.status != SourceCheckStatus.FETCHED)
    if not evidence:
        return RetrievalStatus.BLOCKED if blocked else RetrievalStatus.NO_EVIDENCE
    if failed_count or not requirements:
        return RetrievalStatus.PARTIAL
    return RetrievalStatus.COMPLETED


def _empty_result(
    request: InformationRetrievalRequest,
    status: RetrievalStatus,
    warnings: list[str],
    mode: ProcessingMode,
) -> RetrievedEvidenceResult:
    return RetrievedEvidenceResult(
        contract_version=CONTRACT_VERSION,
        request_id=request.request_id,
        intent_request_id=request.intent.request_id,
        profile_context_request_id=request.profile_context.request_id,
        service_name=request.intent.service_name,
        task_type=request.intent.task_type,
        jurisdiction=request.intent.jurisdiction,
        retrieval_status=status,
        search_queries=[],
        unanswered_questions=_unanswered(request, []),
        warnings=warnings,
        processing_mode=mode,
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return out
