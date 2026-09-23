"""
Evidence Ranker and Grounding Verifier for Information Retrieval Agent.
Performs deterministic signal-based evidence scoring, grounding validation, and tie-breaking sorting.
"""
import logging
from typing import List, Dict, Any, Optional
from agents.knowledge_based.information_retrieval.schemas.evidence import Evidence, GroundingStatus
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry
from agents.knowledge_based.information_retrieval.retrieval.fusion import FreshnessType

logger = logging.getLogger(__name__)


class GroundingVerifier:
    """
    Validates whether candidate evidence items are grounded in trusted authoritative sources
    and traceable to specific document/page or live web provenance.
    """

    def __init__(self, source_registry: Optional[SourceRegistry] = None):
        self.registry = source_registry or SourceRegistry(include_defaults=True)

    def verify_grounding(self, evidence: Evidence) -> GroundingStatus:
        """
        Verifies evidence passage traceability, content non-emptiness, and source domain authority.
        """
        if not evidence or not evidence.passage or len(evidence.passage.strip()) < 20:
            return GroundingStatus.INVALID

        if not evidence.source or not evidence.source.source_id or not evidence.source.url:
            return GroundingStatus.INVALID

        # Domain Authority Validation
        domain = evidence.source.domain or "aadhaar"
        if not self.registry.is_authoritative(evidence.source.url, domain):
            logger.warning(f"Evidence '{evidence.evidence_id}' failed grounding: domain '{evidence.source.url}' is untrusted")
            return GroundingStatus.INVALID

        # Check requirement association metadata
        reqs = evidence.metadata.get("associated_requirements", [])
        if not reqs and not evidence.metadata.get("category"):
            return GroundingStatus.INVALID

        return GroundingStatus.VERIFIED_GROUNDED


class EvidenceRanker:
    """
    Deterministically scores and ranks candidate evidence using explicit, inspectable signals:
    - Semantic Relevance (35%)
    - Source Authority (25%)
    - Freshness (15%)
    - Requirement Relevance (15%)
    - Text Completeness (10%)
    """

    def __init__(
        self,
        verifier: Optional[GroundingVerifier] = None,
        w_semantic: float = 0.35,
        w_authority: float = 0.25,
        w_freshness: float = 0.15,
        w_requirement: float = 0.15,
        w_completeness: float = 0.10,
    ):
        self.verifier = verifier or GroundingVerifier()
        self.w_semantic = w_semantic
        self.w_authority = w_authority
        self.w_freshness = w_freshness
        self.w_requirement = w_requirement
        self.w_completeness = w_completeness

    def rank_and_verify(
        self,
        evidence_list: List[Evidence],
    ) -> List[Evidence]:
        """
        Verifies grounding, calculates deterministic ranking scores, and sorts evidence deterministically.
        """
        if not evidence_list:
            return []

        processed: List[Evidence] = []

        for ev in evidence_list:
            # 1. Grounding Verification
            status = self.verifier.verify_grounding(ev)
            ev.grounding_status = status

            if status == GroundingStatus.INVALID:
                ev.ranking_score = 0.0
                processed.append(ev)
                continue

            # 2. Compute Explicit Signals
            s_sem = self._compute_semantic_signal(ev)
            s_auth = self._compute_authority_signal(ev)
            s_fresh = self._compute_freshness_signal(ev)
            s_req = self._compute_requirement_signal(ev)
            s_comp = self._compute_completeness_signal(ev)

            # 3. Weighted Ranking Formula
            score = (
                (self.w_semantic * s_sem)
                + (self.w_authority * s_auth)
                + (self.w_freshness * s_fresh)
                + (self.w_requirement * s_req)
                + (self.w_completeness * s_comp)
            )

            # Normalize to [0.0, 1.0]
            score = max(0.0, min(1.0, round(score, 4)))
            ev.ranking_score = score

            # Store inspectable signal breakdown in metadata
            ev.metadata["ranking_signals"] = {
                "semantic": round(s_sem, 4),
                "authority": round(s_auth, 4),
                "freshness": round(s_fresh, 4),
                "requirement": round(s_req, 4),
                "completeness": round(s_comp, 4),
            }

            processed.append(ev)

        # 4. Deterministic Tie-Breaking Sort
        # Primary: ranking_score DESC, Secondary: source_id ASC, Tertiary: evidence_id ASC
        sorted_evidence = sorted(
            processed,
            key=lambda item: (-item.ranking_score, item.source.source_id, item.evidence_id),
        )

        return sorted_evidence

    def _compute_semantic_signal(self, ev: Evidence) -> float:
        """Normalizes ChromaDB vector relevance score [0.0, 1.0]."""
        return max(0.0, min(1.0, float(ev.relevance_score)))

    def _compute_authority_signal(self, ev: Evidence) -> float:
        """Extracts source trust level from Source metadata [0.0, 1.0]."""
        if ev.source and hasattr(ev.source, "trust_level"):
            return max(0.0, min(1.0, float(ev.source.trust_level)))
        return 0.8  # Default for official government source

    def _compute_freshness_signal(self, ev: Evidence) -> float:
        """Scores evidence freshness based on retrieval origin."""
        fresh_type = ev.metadata.get("freshness_type", FreshnessType.UNKNOWN_FRESHNESS.value)
        if fresh_type == FreshnessType.LIVE_CURRENT_RETRIEVAL.value:
            return 1.0
        elif fresh_type == FreshnessType.STORED_OFFICIAL_DOCUMENT.value:
            return 0.85
        return 0.50

    def _compute_requirement_signal(self, ev: Evidence) -> float:
        """Evaluates term relevance between category topic and passage text."""
        category = str(ev.metadata.get("category", "")).lower()
        if not category:
            return 0.5

        passage_lower = ev.passage.lower()
        terms = [t for t in category.split("_") if len(t) > 2]
        if not terms:
            return 0.5

        matches = sum(1 for t in terms if t in passage_lower)
        return min(1.0, max(0.2, matches / len(terms)))

    def _compute_completeness_signal(self, ev: Evidence) -> float:
        """Evaluates text length usability and provenance richness."""
        text_len = len(ev.passage.strip())
        len_score = min(1.0, text_len / 300.0)
        has_page_or_title = 0.2 if (ev.page_number or ev.source.document_title) else 0.0
        return min(1.0, len_score * 0.8 + has_page_or_title)
