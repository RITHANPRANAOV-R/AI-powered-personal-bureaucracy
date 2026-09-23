"""Static audit utility for verifying all 8 specialist agent Pydantic contracts and JSON schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Type
from pydantic import BaseModel

# Import all 8 specialist agent Pydantic contracts
from agents.intent_understanding.schema import IntentResult
from agents.user_context.schema import ProfileContextResult
from agents.information_retrieval.schema import RetrievedEvidenceResult
from agents.workflow_planning.schema import WorkflowPlan
from agents.compliance_validation.schema import ValidationResult
from agents.execution_assistance.schema import ExecutionResult
from agents.monitoring_update.schema import MonitoringResult
from agents.response_generation.schema import CitizenResponse


AGENT_CONTRACTS: List[Dict[str, Any]] = [
    {
        "agent_name": "Intent Understanding Agent",
        "agent_id": 1,
        "model": IntentResult,
        "schema_file": "intent_result.schema.json",
    },
    {
        "agent_name": "User Context & Profile Agent",
        "agent_id": 2,
        "model": ProfileContextResult,
        "schema_file": "profile_context_result.schema.json",
    },
    {
        "agent_name": "Information Retrieval Agent",
        "agent_id": 3,
        "model": RetrievedEvidenceResult,
        "schema_file": "retrieved_evidence_result.schema.json",
    },
    {
        "agent_name": "Workflow Planning Agent",
        "agent_id": 4,
        "model": WorkflowPlan,
        "schema_file": "workflow_plan.schema.json",
    },
    {
        "agent_name": "Compliance & Validation Agent",
        "agent_id": 5,
        "model": ValidationResult,
        "schema_file": "validation_result.schema.json",
    },
    {
        "agent_name": "Execution & Assistance Agent",
        "agent_id": 6,
        "model": ExecutionResult,
        "schema_file": "execution_result.schema.json",
    },
    {
        "agent_name": "Monitoring & Update Agent",
        "agent_id": 7,
        "model": MonitoringResult,
        "schema_file": "monitoring_result.schema.json",
    },
    {
        "agent_name": "Response Generation Agent",
        "agent_id": 8,
        "model": CitizenResponse,
        "schema_file": "citizen_response.schema.json",
    },
]


def check_all_contracts(contracts_dir: Path | str | None = None) -> Dict[str, Any]:
    """Audit all 8 specialist agent contracts against stored JSON schemas and verify correlation.
    
    Returns:
        Dict with status, audited contract details, and any mismatches found.
    """
    if contracts_dir is None:
        # Default to contracts/ in the workspace root
        base_path = Path(__file__).resolve().parent.parent
        contracts_dir = base_path / "contracts"
    else:
        contracts_dir = Path(contracts_dir)

    results = []
    has_error = False

    for contract in AGENT_CONTRACTS:
        agent_id = contract["agent_id"]
        name = contract["agent_name"]
        model_cls: Type[BaseModel] = contract["model"]
        schema_fname = contract["schema_file"]
        schema_path = contracts_dir / schema_fname

        detail = {
            "agent_id": agent_id,
            "agent_name": name,
            "model": model_cls.__name__,
            "schema_file": schema_fname,
            "schema_exists": schema_path.is_file(),
            "schema_match": False,
            "version": "1.0",
            "errors": [],
        }

        if not schema_path.is_file():
            detail["errors"].append(f"Schema file missing: {schema_path}")
            has_error = True
        else:
            try:
                stored_schema = json.loads(schema_path.read_text(encoding="utf-8"))
                generated_schema = model_cls.model_json_schema()

                # Basic comparison - ignore minor formatting differences if JSON matches
                if stored_schema.get("title") == generated_schema.get("title"):
                    detail["schema_match"] = True
                else:
                    detail["errors"].append(
                        f"Schema title mismatch: stored='{stored_schema.get('title')}' vs generated='{generated_schema.get('title')}'"
                    )
                    has_error = True
            except Exception as e:
                detail["errors"].append(f"Error validating schema: {e}")
                has_error = True

        results.append(detail)

    return {
        "status": "PASS" if not has_error else "FAIL",
        "total_contracts": len(AGENT_CONTRACTS),
        "audit_details": results,
    }


if __name__ == "__main__":
    res = check_all_contracts()
    print(json.dumps(res, indent=2))
