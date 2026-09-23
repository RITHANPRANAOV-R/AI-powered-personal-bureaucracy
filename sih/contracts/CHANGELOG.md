# Bureaucracy Assistant Agent Contracts Changelog

## [1.0.0] - 2026-09-24

### Agent Contract Audit & Alignment Summary
All 8 specialist agent contracts have been audited, updated, and validated for complete cross-agent correlation and schema compliance.

### Specialist Agent Contracts:
1. **Agent 1: Intent Understanding Agent** (`IntentResult`)
   - Schema File: `contracts/intent_result.schema.json`
   - Contract Version: `1.0`
   - Key Handoff Fields: `request_id`, `task_type`, `user_intent`, `target_service`, `status`, `extracted_slots`, `ambiguity_level`.

2. **Agent 2: User Context & Profile Agent** (`ProfileContextResult`)
   - Schema File: `contracts/profile_context_result.schema.json`
   - Contract Version: `1.0`
   - Key Handoff Fields: `request_id`, `profile_id`, `resolved_facts`, `missing_required_facts`, `vault_documents`, `consent_status`.

3. **Agent 3: Information Retrieval Agent** (`RetrievedEvidenceResult`)
   - Schema File: `contracts/retrieved_evidence_result.schema.json`
   - Contract Version: `1.0`
   - Key Handoff Fields: `request_id`, `evidence_items` (`title`, `canonical_url`, `extracted_rules`, `fees`, `required_documents`, `freshness_timestamp`, `trust_score`).

4. **Agent 4: Workflow Planning Agent** (`WorkflowPlan`)
   - Schema File: `contracts/workflow_plan.schema.json`
   - Contract Version: `1.0`
   - Key Handoff Fields: `request_id`, `workflow_id`, `goal`, `steps` (`step_id`, `title`, `agent_role`, `action_type`, `prerequisites`, `allows_automation`, `risk_level`), `status`.

5. **Agent 5: Compliance & Validation Agent** (`ValidationResult`)
   - Schema File: `contracts/validation_result.schema.json`
   - Contract Version: `1.0`
   - Key Handoff Fields: `request_id`, `overall_decision` (`APPROVE`, `NEEDS_HUMAN_FACT`, `BLOCK`), `checks` (`rule_id`, `status`, `reasons`, `violating_fields`), `missing_facts`.

6. **Agent 6: Execution & Assistance Agent** (`ExecutionResult`)
   - Schema File: `contracts/execution_result.schema.json`
   - Contract Version: `1.0`
   - Key Handoff Fields: `request_id`, `workflow_id`, `step_id`, `status` (`SUCCESS`, `PAUSED_FOR_USER`, `FAILED`), `captcha_detected`, `submitted`, `confirmation_reference`.

7. **Agent 7: Monitoring & Update Agent** (`MonitoringResult`)
   - Schema File: `contracts/monitoring_result.schema.json`
   - Contract Version: `1.0`
   - Key Handoff Fields: `request_id`, `application_id`, `status` (`SUBMITTED`, `UNDER_PROCESS`, `ACTION_REQUIRED`, `COMPLETED`), `last_checked_at`, `status_history`.

8. **Agent 8: Response Generation Agent** (`CitizenResponse`)
   - Schema File: `contracts/citizen_response.schema.json`
   - Contract Version: `1.0`
   - Key Handoff Fields: `request_id`, `workflow_id`, `summary`, `actionable_steps`, `user_prompts`, `raw_payload`, `timestamp`.

### Core Handoff Guarantees:
- Every agent response includes `request_id` correlation string.
- All JSON schema files in `contracts/` are generated directly from Pydantic models via `model_json_schema()`.
- Static audit can be run at any time via `python -m src.bureaucracy_agent.orchestrator.cli contracts-check`.
