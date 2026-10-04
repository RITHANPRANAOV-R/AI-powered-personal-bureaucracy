from typing import Dict, Any, List


def structure_medical_json(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes multi-page vision output into a single
    medical-friendly schema for downstream agents.
    """

    pages = raw.get("pages", [])

    all_findings: List[str] = []
    detected_types = set()
    quality_warnings: List[str] = []

    structured_pages = []

    for p in pages:
        vision = p.get("vision_analysis", {})

        doc_type = vision.get("document_type")
        if doc_type:
            detected_types.add(doc_type)

        findings = vision.get("key_findings") or []
        if isinstance(findings, list):
            all_findings.extend(findings)

        warnings = vision.get("any_warnings_about_quality") or []
        if isinstance(warnings, list):
            quality_warnings.extend(warnings)

        structured_pages.append({
            "page_index": p.get("page_index"),
            "model_used": p.get("model_used"),
            "ocr_confidence": p.get("ocr_confidence"),
            "document_type": doc_type,
            "key_findings": findings,
            "detected_fields": vision.get("detected_fields"),
            "raw_ocr_text": p.get("ocr_text"),
        })

    return {
        "source_file": raw.get("source_file"),
        "num_pages": raw.get("num_pages"),
        "detected_document_types": sorted(detected_types),
        "aggregate_findings": all_findings,
        "quality_warnings": quality_warnings,
        "pages": structured_pages,
        "meta": {
            "pipeline": "person1_preprocessing",
            "purpose": "medical_document_understanding",
        },
    }
