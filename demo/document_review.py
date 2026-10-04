from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.orchestration.document_input import AadhaarDocumentInput, AadhaarDocumentService, ExtractionStatus


DISPLAY_FIELDS = (
    ("name", "Name"),
    ("date_of_birth", "Date of birth"),
    ("gender", "Gender"),
    ("masked_aadhaar", "Aadhaar"),
    ("existing_address", "Existing address"),
)


def _print_extracted(data) -> None:
    print("\nReview extracted information")
    for field_name, label in DISPLAY_FIELDS:
        field = getattr(data, field_name)
        print(f"{label}: {field.value if field is not None else '[not extracted]'}")
    print("\nThese details were extracted from your document. Please verify them before continuing.")


def run_review(file_path: str, session_id: str = "document-review-session") -> int:
    path = Path(file_path)
    try:
        content = path.read_bytes()
    except OSError:
        print("Could not read the selected document.")
        return 1

    service = AadhaarDocumentService()
    extraction = service.extract(AadhaarDocumentInput(filename=path.name, content=content))
    if extraction.status != ExtractionStatus.SUCCESS:
        print(f"Document review stopped: {extraction.error or extraction.status.value}.")
        if extraction.missing_fields:
            print(f"Please provide manually: {', '.join(extraction.missing_fields)}")
        return 1

    _print_extracted(extraction.data)
    choice = input("\n[Confirm details] [Correct details] (c/r): ").strip().lower()
    corrections = {}
    if choice == "r":
        field_name = input("Field to correct: ").strip()
        corrected_value = input("Correct value: ").strip()
        corrections[field_name] = corrected_value
    elif choice != "c":
        print("Confirmation was not provided. No downstream facts were created.")
        return 1

    try:
        confirmed = service.confirm(extraction, corrections)
    except ValueError as error:
        print(f"Confirmation stopped: {error}")
        return 1

    context = confirmed.to_execution_context(session_id)
    print("\nYour Aadhaar details are confirmed.")
    print(json.dumps(context.model_dump(mode="json"), indent=2))
    print("This confirmed context is ready to be passed to the existing pipeline.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Review extracted Aadhaar details locally.")
    parser.add_argument("document", help="Path to a local Aadhaar PDF or image")
    parser.add_argument("--session-id", default="document-review-session")
    args = parser.parse_args()
    return run_review(args.document, args.session_id)


if __name__ == "__main__":
    raise SystemExit(main())
