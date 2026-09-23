import os
from typing import Dict, Any

from .preprocess_document import preprocess_document
from .json_structuring import structure_medical_json


def process_file(input_path: str) -> Dict[str, Any]:
    """
    Public API for Person-1.
    Takes any supported medical file and returns
    structured preprocessing output.
    """
    raw = preprocess_document(input_path)
    structured = structure_medical_json(raw)
    return structured


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to PDF/Image/DICOM")
    parser.add_argument("--out", default="output.json", help="Output JSON path")
    args = parser.parse_args()

    result = process_file(args.input)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Saved structured output to {args.out}")
