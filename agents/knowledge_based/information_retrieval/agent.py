"""
Information Retrieval Agent Top-Level Orchestrator.
Exposes a unified interface for Intent Understanding Agent and Workflow Planning Agent,
orchestrating Official Stored RAG, Official Live Fetch, User Document Understanding,
Requirement ↔ Document Linking, and Cross-Evidence Synthesis.
"""
import os
import logging
from typing import Optional, List, Union, Any, Dict

from agents.knowledge_based.information_retrieval.config import RetrievalConfig, default_config
from agents.knowledge_based.information_retrieval.schemas import (
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatus,
    WarningItem,
    UserDocument,
    UserDocumentInput,
    DocumentType,
    ExtractedField,
    ExtractionMethod,
    OCRStatus,
)
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry
from agents.knowledge_based.information_retrieval.retrieval.hybrid_retriever import (
    HybridRetriever,
    RetrievalMode,
)
from agents.knowledge_based.information_retrieval.document_understanding.pipeline import UserDocumentPipeline
from agents.knowledge_based.information_retrieval.retrieval.linker import RequirementDocumentLinker
from agents.knowledge_based.information_retrieval.retrieval.fusion import EvidenceFusionEngine

logger = logging.getLogger(__name__)


class InformationRetrievalAgent:
    """
    Top-Level Orchestrator for Information Retrieval Agent.
    Coordinates Query Construction, Hybrid Retrieval (ChromaDB + Live HTTP),
    User Document Understanding, Requirement ↔ Document Linking, Evidence Fusion,
    Deterministic Signal Ranking, and Grounding Verification.
    """

    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        hybrid_retriever: Optional[HybridRetriever] = None,
        source_registry: Optional[SourceRegistry] = None,
        doc_pipeline: Optional[UserDocumentPipeline] = None,
        linker: Optional[RequirementDocumentLinker] = None,
        fusion_engine: Optional[EvidenceFusionEngine] = None,
        default_mode: RetrievalMode = RetrievalMode.HYBRID,
    ):
        self.config = config or default_config
        self.source_registry = source_registry or SourceRegistry(include_defaults=True)
        self.hybrid_retriever = hybrid_retriever or HybridRetriever(
            source_registry=self.source_registry,
            default_mode=default_mode,
        )
        self.doc_pipeline = doc_pipeline or UserDocumentPipeline()
        self.linker = linker or RequirementDocumentLinker()
        self.fusion_engine = fusion_engine or EvidenceFusionEngine()
        self.default_mode = default_mode

    def retrieve(
        self,
        request: RetrievalRequest,
        user_documents: Optional[List[Any]] = None,
        mode: Optional[RetrievalMode] = None,
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        """
        Main public interface for executing information retrieval requests.

        Args:
            request: Structured RetrievalRequest specification from Intent Understanding Agent.
            user_documents: Optional list of user document files (file paths, UserDocument objects, or UserDocumentInput items).
            mode: Optional RetrievalMode override (KNOWLEDGE_ONLY, LIVE_ONLY, HYBRID).
            top_k: Optional top-k candidate limit for vector retrieval.

        Returns:
            RetrievalResult containing ranked, grounded evidence, user evidence, linking metadata,
            and source metadata for Workflow Planning Agent.
        """
        effective_mode = mode or self.default_mode

        # 1. Request Validation
        validation_warning = self._validate_request(request)
        if validation_warning and validation_warning.code == "INVALID_REQUEST":
            logger.error("Retrieval request validation failed: request is null or missing request_id")
            return RetrievalResult(
                result_id="res_invalid",
                request_id="unknown",
                service="unknown",
                domain="unknown",
                retrieval_status=RetrievalStatus.FAILED,
                warnings=[validation_warning],
            )

        # Apply fallback domain if unassigned
        if not request.domain:
            request.domain = "aadhaar"

        req_count = len(request.requirements) if request.requirements else len(request.information_needed or [])
        logger.info(
            f"Orchestrating retrieval for request '{request.request_id}' | "
            f"Service: '{request.service}' | Domain: '{request.domain}' | "
            f"Mode: '{effective_mode.value}' | Requirements: {req_count}"
        )

        # 2. Orchestrate Official Retrieval Pipeline (ChromaDB + Live HTTP + Ranking + Grounding)
        try:
            result = self.hybrid_retriever.retrieve(
                request=request,
                mode=effective_mode,
                top_k=top_k,
            )
        except Exception as e:
            logger.exception(f"Unhandled retrieval exception for request '{request.request_id}': {e}")
            return RetrievalResult(
                result_id=f"res_{request.request_id}",
                request_id=request.request_id,
                service=request.service or "general",
                domain=request.domain or "aadhaar",
                retrieval_status=RetrievalStatus.FAILED,
                warnings=[
                    WarningItem(
                        warning_id=f"warn_err_{request.request_id}",
                        code="ORCHESTRATION_ERROR",
                        message=f"Retrieval orchestration encountered unhandled error: {str(e)}",
                    )
                ],
            )

        if validation_warning:
            result.warnings.append(validation_warning)

        # 3. Process User Documents (if provided directly or via request.user_documents)
        raw_doc_inputs = user_documents if user_documents is not None else request.user_documents
        processed_user_docs: List[UserDocument] = []

        if raw_doc_inputs:
            for item in raw_doc_inputs:
                try:
                    parsed_doc = self._parse_user_document_item(item)
                    if parsed_doc:
                        processed_user_docs.append(parsed_doc)
                except Exception as doc_err:
                    logger.warning(f"User document processing failed for item {item}: {doc_err}")
                    result.warnings.append(
                        WarningItem(
                            warning_id=f"warn_doc_parse_{len(result.warnings)+1}",
                            code="USER_DOCUMENT_PARSE_FAILED",
                            message=f"Failed to process user document item: {str(doc_err)}",
                        )
                    )

        # 4. Requirement ↔ User Document Linking (if user documents present)
        linking_result = None
        if processed_user_docs:
            try:
                linking_result = self.linker.link(
                    retrieval_result=result,
                    user_documents=processed_user_docs,
                )
            except Exception as link_err:
                logger.warning(f"Requirement-document linking failed: {link_err}")
                result.warnings.append(
                    WarningItem(
                        warning_id=f"warn_linker_{len(result.warnings)+1}",
                        code="LINKER_FAILED",
                        message=f"Requirement-document linking encountered an error: {str(link_err)}",
                    )
                )

        # 5. Cross-Evidence Synthesis & Fusion (Merge Official, User, and Linking Evidence)
        if processed_user_docs or linking_result:
            try:
                fused_ev, fused_sources, fused_conflicts = self.fusion_engine.fuse_evidence(
                    knowledge_evidence=result.evidence,
                    live_evidence=[],  # Already fused by HybridRetriever inside result.evidence
                    user_documents=processed_user_docs,
                    linking_result=linking_result,
                )
                result.evidence = fused_ev
                # Combine unique sources
                existing_src_ids = {s.source_id for s in result.sources}
                for src in fused_sources:
                    if src.source_id not in existing_src_ids:
                        result.sources.append(src)
                        existing_src_ids.add(src.source_id)

                # Merge conflicts
                if fused_conflicts:
                    existing_conf_ids = {c.conflict_id for c in result.conflicts}
                    for conf in fused_conflicts:
                        if conf.conflict_id not in existing_conf_ids:
                            result.conflicts.append(conf)
                            existing_conf_ids.add(conf.conflict_id)
            except Exception as fuse_err:
                logger.warning(f"Cross-evidence fusion failed: {fuse_err}")
                result.warnings.append(
                    WarningItem(
                        warning_id=f"warn_fuse_{len(result.warnings)+1}",
                        code="EVIDENCE_FUSION_FAILED",
                        message=f"Cross-evidence fusion encountered an error: {str(fuse_err)}",
                    )
                )

        # 6. Diagnostic Summary
        grounded_count = sum(1 for ev in result.evidence if getattr(ev, "grounding_status", None) == "verified_grounded")
        logger.info(
            f"Retrieval completed for '{request.request_id}' | Status: '{result.retrieval_status}' | "
            f"Returned Evidence: {len(result.evidence)} | Grounded: {grounded_count} | "
            f"User Docs Processed: {len(processed_user_docs)} | "
            f"Conflicts: {len(result.conflicts)} | Warnings: {len(result.warnings)}"
        )

        return result

    def _parse_user_document_item(self, item: Any) -> UserDocument:
        """Helper to convert various user document input representations into UserDocument schema."""
        if isinstance(item, UserDocument):
            return item

        if isinstance(item, UserDocumentInput):
            if item.file_path and os.path.exists(item.file_path):
                return self.doc_pipeline.process_document(
                    file_path=item.file_path,
                    doc_type=item.document_type,
                    document_id=item.document_id,
                )
            elif item.extracted_fields:
                # Convert pre-extracted fields in UserDocumentInput directly to UserDocument
                fields_dict: Dict[str, ExtractedField] = {}
                for f_name, f_val in item.extracted_fields.items():
                    if isinstance(f_val, ExtractedField):
                        fields_dict[f_name] = f_val
                    elif isinstance(f_val, dict):
                        fields_dict[f_name] = ExtractedField(
                            field_name=f_name,
                            value=str(f_val.get("value", "")),
                            confidence=float(f_val.get("confidence", 1.0)),
                            page_number=int(f_val.get("page_number", 1)),
                        )
                    else:
                        fields_dict[f_name] = ExtractedField(
                            field_name=f_name,
                            value=str(f_val),
                            confidence=0.90,
                            page_number=1,
                        )

                return UserDocument(
                    document_id=item.document_id,
                    filename=os.path.basename(item.file_path) if item.file_path else f"{item.document_id}.pdf",
                    mime_type=".pdf",
                    document_type=item.document_type,
                    classification_confidence=0.90,
                    extraction_method=ExtractionMethod.DIRECT_TEXT_PDF,
                    ocr_status=OCRStatus.NOT_REQUIRED,
                    extracted_fields=fields_dict,
                )
            else:
                raise ValueError(f"UserDocumentInput contains neither existing file path nor extracted_fields: {item}")

        if isinstance(item, str):
            if os.path.exists(item):
                return self.doc_pipeline.process_document(file_path=item)
            else:
                raise FileNotFoundError(f"User document file path does not exist: {item}")

        raise ValueError(f"Unrecognized user document item type: {type(item)}")

    def _validate_request(self, request: Optional[RetrievalRequest]) -> Optional[WarningItem]:
        """Validates incoming RetrievalRequest for structural integrity."""
        if not request or not request.request_id:
            return WarningItem(
                warning_id="warn_invalid_request",
                code="INVALID_REQUEST",
                message="RetrievalRequest object is null or missing request_id",
            )

        if not request.service and not request.goal:
            return WarningItem(
                warning_id="warn_missing_service",
                code="MISSING_SERVICE_SPECIFICATION",
                message="RetrievalRequest lacks explicit service or goal specification",
            )

        return None
