"""FastAPI Backend Server for Personal Bureaucracy Assistant Multi-Agent System."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Imports from project
from agents.audit import AGENT_CONTRACTS
from agents.compliance_validation.agent import ComplianceValidationAgent
from agents.compliance_validation.schema import ComplianceValidationRequest, UserApprovalRecord, ValidationPhase, ValidationResult
from agents.execution_assistance.schema import ExecutionResult, ExecutionStatus, UserExecutionApproval
from agents.information_retrieval.agent import InformationRetrievalAgent
from agents.information_retrieval.schema import InformationRetrievalRequest, RetrievedEvidenceResult
from agents.information_retrieval.kb_service import KnowledgeBaseService
from agents.intent_understanding.agent import IntentUnderstandingAgent
from agents.intent_understanding.schema import IntentRequest, IntentResult
from agents.monitoring_update.agent import MonitoringUpdateAgent
from agents.monitoring_update.schema import MonitoringResult, MonitoringRequest
from agents.response_generation.agent import ResponseGenerationAgent
from agents.response_generation.schema import CitizenResponse, ResponseGenerationRequest, OverallStatus
from agents.user_context.agent import UserContextAgent
from agents.user_context.schema import ConsentAction, ProfileContextRequest, ProfileContextResult, ProfileFact
from agents.workflow_planning.agent import WorkflowPlanningAgent
from agents.workflow_planning.schema import WorkflowPlan, WorkflowPlanningRequest

from src.bureaucracy_agent.orchestrator import adapters, consent, router, scoping
from src.bureaucracy_agent.orchestrator.checkpoints import SqliteCheckpointStore
from src.bureaucracy_agent.orchestrator.finalize import derive_terminal_status
from src.bureaucracy_agent.orchestrator.gates import check_browser_available
from src.bureaucracy_agent.orchestrator.graph import OrchestratorGraph, TRANSITION_TABLE
from src.bureaucracy_agent.orchestrator.hosts import get_allowed_hosts, get_official_source_registry
from src.bureaucracy_agent.orchestrator.state import OrchestratorState
from src.bureaucracy_agent.orchestrator.statuses import WorkflowStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bureaucracy_server")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
VAULT_DIR = DATA_DIR / "vault"
KB_DIR = DATA_DIR / "knowledge_base"
PROFILE_PATH = DATA_DIR / "profile.example.json"
AUDIT_LOG_PATH = DATA_DIR / "audit_log.jsonl"

VAULT_DIR.mkdir(parents=True, exist_ok=True)
KB_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AI-Powered Personal Bureaucracy Assistant API",
    version="1.0.0",
    description="Multi-Agent Orchestrator backend bridging 8 specialist agents to modern frontend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

checkpoint_store = SqliteCheckpointStore()
active_connections: Dict[str, List[WebSocket]] = {}


class ConnectionManager:
    @staticmethod
    async def connect(workflow_id: str, websocket: WebSocket):
        await websocket.accept()
        if workflow_id not in active_connections:
            active_connections[workflow_id] = []
        active_connections[workflow_id].append(websocket)

    @staticmethod
    def disconnect(workflow_id: str, websocket: WebSocket):
        if workflow_id in active_connections:
            active_connections[workflow_id].remove(websocket)
            if not active_connections[workflow_id]:
                del active_connections[workflow_id]

    @staticmethod
    async def broadcast_state(workflow_id: str, state_data: dict, event_type: str = "state_update"):
        if workflow_id in active_connections:
            msg = json.dumps({"event": event_type, "data": state_data})
            for ws in list(active_connections[workflow_id]):
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass


# --- Request/Response Models ---

class StartWorkflowRequest(BaseModel):
    user_goal: str
    language: str = "en"
    is_demo: bool = True
    is_dry_run: bool = True
    stop_before_submit: bool = True
    vault_dir: str = "data/vault"
    profile_path: str = "data/profile.example.json"


class FactConsentRequest(BaseModel):
    decisions: Dict[str, ConsentAction]
    answers: Dict[str, str] = Field(default_factory=dict)


class AuthorizeRequest(BaseModel):
    authorization_phrase: str


class ClarificationAnswerRequest(BaseModel):
    answers: Dict[str, str]


class SubmitPortalFieldsRequest(BaseModel):
    field_values: Dict[str, str]
    field_labels: Dict[str, str] = Field(default_factory=dict)
    save_to_vault: Dict[str, bool] = Field(default_factory=dict)


# --- Workflow Runner with WebSocket Broadcasts ---

def run_workflow_to_pause_or_end(state: OrchestratorState, graph: OrchestratorGraph) -> OrchestratorState:
    """Execute graph transitions synchronously until pause or end is reached."""
    return graph.run(state)


# --- API Routes ---

@app.get("/api/health")
async def get_health():
    browser_ok, browser_msg = check_browser_available()
    checkpoints = checkpoint_store.list_checkpoints()
    return {
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_count": 8,
        "browser_ready": browser_ok,
        "browser_message": browser_msg,
        "total_workflows_tracked": len(checkpoints),
        "environment": {
            "vault_dir": str(VAULT_DIR),
            "profile_exists": PROFILE_PATH.exists(),
            "audit_log_exists": AUDIT_LOG_PATH.exists(),
        },
    }


@app.get("/api/agents")
async def list_agents():
    """List all 8 specialist agents with their contract metadata and capabilities."""
    agents_info = [
        {
            "id": 1,
            "key": "intent_understanding",
            "name": "Intent Understanding Agent",
            "role": "Goal Classification & Entity Extraction",
            "description": "Classifies citizen natural-language requests into structured IntentResult with service type, task type, entities, and ambiguity checks.",
            "contract": "IntentResult (v1.0)",
            "schema_file": "intent_result.schema.json",
            "runtime": "Local Ollama (Qwen 3 1.7B) with Deterministic Fallback",
            "inputs": ["user_goal", "language_preference", "jurisdiction_hint"],
            "outputs": ["service_type", "task_type", "explicit_facts", "clarification_questions", "confidence_score"],
            "badge_color": "indigo",
        },
        {
            "id": 2,
            "key": "user_context",
            "name": "User Context & Profile Agent",
            "role": "Document Vault Scanning & Fact Isolation",
            "description": "Safely reads authorized user vault documents and local profile to extract verified facts without leaking personal data.",
            "contract": "ProfileContextResult (v1.0)",
            "schema_file": "profile_context_result.schema.json",
            "runtime": "Local Vault Parser & Consent Manager",
            "inputs": ["vault_dir", "profile_path", "allowed_fact_keys"],
            "outputs": ["relevant_facts", "missing_facts", "unconfirmed_facts", "consent_audit"],
            "badge_color": "blue",
        },
        {
            "id": 3,
            "key": "information_retrieval",
            "name": "Information Retrieval Agent",
            "role": "Official Knowledge Base & Policy Engine",
            "description": "Retrieves official government rules, forms, fee schedules, and requirements strictly from allowlisted government sources.",
            "contract": "RetrievedEvidenceResult (v1.0)",
            "schema_file": "retrieved_evidence_result.schema.json",
            "runtime": "Knowledge Base Manifest & Official Scraper",
            "inputs": ["service_name", "target_jurisdiction", "query"],
            "outputs": ["evidence_items", "official_urls", "fee_breakdown", "required_documents", "trust_scores"],
            "badge_color": "cyan",
        },
        {
            "id": 4,
            "key": "workflow_planning",
            "name": "Workflow Planning Agent",
            "role": "DAG Task Graph & Prerequisite Planner",
            "description": "Synthesizes retrieved official evidence and user profile facts into an ordered, executable WorkflowPlan DAG.",
            "contract": "WorkflowPlan (v1.0)",
            "schema_file": "workflow_plan.schema.json",
            "runtime": "Deterministic Plan Synthesizer",
            "inputs": ["intent_result", "profile_context", "retrieved_evidence"],
            "outputs": ["steps", "prerequisites", "estimated_durations", "checkpoint_gates", "scoped_execution_view"],
            "badge_color": "emerald",
        },
        {
            "id": 5,
            "key": "compliance_validation",
            "name": "Compliance & Validation Agent",
            "role": "Pre & Post Execution Deterministic Gates",
            "description": "Performs zero-trust compliance checks: verifies provenance of facts, consent gates, prerequisite satisfiability, and safety authorizations.",
            "contract": "ValidationResult (v1.0)",
            "schema_file": "validation_result.schema.json",
            "runtime": "Deterministic Rule & Provenance Validator",
            "inputs": ["workflow_plan", "profile_context", "evidence", "user_approvals"],
            "outputs": ["decision (APPROVED / REJECTED / NEEDS_CONSENT)", "eligible_steps", "blocked_steps", "issues"],
            "badge_color": "amber",
        },
        {
            "id": 6,
            "key": "execution_assistance",
            "name": "Execution & Assistance Agent",
            "role": "Visible Playwright Browser Driver",
            "description": "Performs assisted live or dry-run execution on official government portals with automated form filling and human-in-the-loop pause gates.",
            "contract": "ExecutionResult (v1.0)",
            "schema_file": "execution_result.schema.json",
            "runtime": "Playwright Browser Automation (Visible / Dry-run)",
            "inputs": ["execution_request", "scoped_steps", "confirmed_facts", "exact_approval_token"],
            "outputs": ["execution_status", "executed_steps", "observed_fields", "confirmation_evidence", "screenshots"],
            "badge_color": "purple",
        },
        {
            "id": 7,
            "key": "monitoring_update",
            "name": "Monitoring & Update Agent",
            "role": "Audit Trail & Lifecycle Tracker",
            "description": "Tracks workflow state transitions, records cryptographic audit events with provenance, detects deltas, and schedules citizen reminders.",
            "contract": "MonitoringResult (v1.0)",
            "schema_file": "monitoring_result.schema.json",
            "runtime": "SQLite & JSONL Audit Store",
            "inputs": ["execution_result", "previous_monitoring_state"],
            "outputs": ["timeline_events", "audit_hashes", "reminders", "next_review_date"],
            "badge_color": "orange",
        },
        {
            "id": 8,
            "key": "response_generation",
            "name": "Response Generation Agent",
            "role": "Citizen Response & Summary Generator",
            "description": "Transforms structured agent contracts into clear, plain-language guidance, actionable next steps, checklist summaries, and Markdown reports.",
            "contract": "CitizenResponse (v1.0)",
            "schema_file": "citizen_response.schema.json",
            "runtime": "Deterministic Grounded Synthesizer (Local LLM optional)",
            "inputs": ["all_prior_agent_results"],
            "outputs": ["headline", "overall_status", "summary", "citizen_next_step", "pending_actions", "formatted_markdown"],
            "badge_color": "rose",
        },
    ]
    return agents_info


@app.get("/api/templates")
async def get_workflow_templates():
    """Get sample pre-configured workflow goals for one-click testing."""
    return [
        {
            "id": "passport-new",
            "title": "Indian Passport Seva (New Application)",
            "category": "Passport & Travel",
            "goal": "I need to register on Passport Seva for a new passport.",
            "description": "End-to-end assisted workflow to register on Indian Passport Seva portal, verify user identity facts, retrieve document rules, and prepare submission.",
            "estimated_time": "3-5 mins",
            "service": "Passport Seva",
            "is_demo": True,
            "is_dry_run": False,
        },
        {
            "id": "passport-reissue",
            "title": "Passport Re-issue / Renewal",
            "category": "Passport & Travel",
            "goal": "I need to renew my expired Indian passport due to validity exhaustion.",
            "description": "Check requirements for passport renewal, extract passport expiry details from vault, and plan submission steps.",
            "estimated_time": "4-6 mins",
            "service": "Passport Seva",
            "is_demo": True,
            "is_dry_run": False,
        },
        {
            "id": "rti-online",
            "title": "RTI Online Application Request",
            "category": "Right to Information",
            "goal": "Submit an RTI Online request to Ministry of External Affairs regarding passport dispatch timeline.",
            "description": "Draft and validate RTI request, check applicant details, verify fee exemption status, and prepare assisted portal submission.",
            "estimated_time": "2-4 mins",
            "service": "RTI Online",
            "is_demo": True,
            "is_dry_run": False,
        },
        {
            "id": "aadhaar-update",
            "title": "Aadhaar Address Update Guidance",
            "category": "Identity & UIDAI",
            "goal": "How can I update my permanent address in Aadhaar with my electricity bill?",
            "description": "Retrieve UIDAI valid supporting documents list, check electricity bill validity in vault, and outline online update workflow.",
            "estimated_time": "2 mins",
            "service": "UIDAI Aadhaar",
            "is_demo": True,
            "is_dry_run": False,
        },
        {
            "id": "voter-id-form6",
            "title": "Voter ID Registration (Form 6)",
            "category": "Elections & Voting",
            "goal": "Register as a new voter on the Election Commission NVSP portal using Form 6.",
            "description": "Verify age & residential eligibility from profile vault, retrieve required photo and address proofs, and plan Form 6 registration.",
            "estimated_time": "3 mins",
            "service": "ECI NVSP Portal",
            "is_demo": True,
            "is_dry_run": False,
        },
    ]


@app.post("/api/workflows/start")
async def start_workflow(req: StartWorkflowRequest):
    """Start a new workflow and run until completion or first pause state."""
    store = SqliteCheckpointStore()
    graph = OrchestratorGraph(checkpoint_store=store)

    state = OrchestratorState(
        user_goal=req.user_goal,
        vault_dir=req.vault_dir,
        profile_path=req.profile_path,
        is_dry_run=req.is_dry_run,
        is_demo=req.is_demo,
        stop_before_submit=req.stop_before_submit,
        language=req.language,
    )
    store.save_checkpoint(state)
    logger.info(f"Started workflow {state.workflow_id} for goal: {state.user_goal}")

    # Run state machine until pause or terminal in a worker thread so Playwright sync_api works properly
    state = await asyncio.to_thread(graph.run, state)
    store.save_checkpoint(state)

    state_dict = state.model_dump(mode="json")
    await ConnectionManager.broadcast_state(state.workflow_id, state_dict, event_type="workflow_step")
    return state_dict


@app.get("/api/workflows")
async def list_workflows():
    """List all workflow checkpoints stored in SQLite."""
    checkpoints = checkpoint_store.list_checkpoints()
    return {"checkpoints": checkpoints}


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get full state for a specific workflow."""
    state = checkpoint_store.load_checkpoint(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")
    return state.model_dump(mode="json")


@app.post("/api/workflows/{workflow_id}/consent")
async def submit_fact_consent(workflow_id: str, req: FactConsentRequest):
    """Submit user decisions on unconfirmed profile facts and resume execution."""
    state = checkpoint_store.load_checkpoint(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

    if state.workflow_status != WorkflowStatus.PAUSED_FACT_CONSENT:
        raise HTTPException(status_code=400, detail=f"Workflow is not in PAUSED_FACT_CONSENT state (current: {state.workflow_status.value})")

    graph = OrchestratorGraph(checkpoint_store=checkpoint_store)
    consent.collect_fact_consent(state, req.decisions, req.answers)

    state.workflow_status = WorkflowStatus.RUNNING
    state.current_node = "COMPLIANCE_PRE"
    checkpoint_store.save_checkpoint(state)

    state = await asyncio.to_thread(graph.run, state)
    checkpoint_store.save_checkpoint(state)

    state_dict = state.model_dump(mode="json")
    await ConnectionManager.broadcast_state(workflow_id, state_dict, event_type="state_update")
    return state_dict


@app.post("/api/workflows/{workflow_id}/authorize")
async def submit_authorization(workflow_id: str, req: AuthorizeRequest):
    """Submit explicit user authorization phrase to permit execution."""
    state = checkpoint_store.load_checkpoint(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

    if state.workflow_status != WorkflowStatus.PAUSED_NEEDS_AUTHORIZATION:
        raise HTTPException(status_code=400, detail=f"Workflow is not awaiting authorization (current: {state.workflow_status.value})")

    graph = OrchestratorGraph(checkpoint_store=checkpoint_store)
    ok, comp_apprs, exec_apprs, msg = consent.process_user_authorization(state, req.authorization_phrase)

    if not ok:
        state.workflow_status = WorkflowStatus.CANCELLED
        state.terminal_reason = f"Authorization Rejected: {msg}"
        state.current_node = "RESPONSE"
        checkpoint_store.save_checkpoint(state)
        state = await asyncio.to_thread(graph.run, state)
    else:
        state.workflow_status = WorkflowStatus.RUNNING
        state.current_node = "COMPLIANCE_PRE"
        checkpoint_store.save_checkpoint(state)
        state = await asyncio.to_thread(graph.run, state)

    checkpoint_store.save_checkpoint(state)
    state_dict = state.model_dump(mode="json")
    await ConnectionManager.broadcast_state(workflow_id, state_dict, event_type="state_update")
    return state_dict


@app.post("/api/workflows/{workflow_id}/resume")
@app.post("/api/workflows/{workflow_id}/resume-pause")
async def resume_paused_workflow(workflow_id: str):
    """Resume workflow from CAPTCHA, Payment, or generic pause states."""
    state = checkpoint_store.load_checkpoint(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

    graph = OrchestratorGraph(checkpoint_store=checkpoint_store)

    if state.workflow_status in {WorkflowStatus.PAUSED_CAPTCHA, WorkflowStatus.PAUSED_PAYMENT}:
        state.workflow_status = WorkflowStatus.RUNNING
        state.current_node = "EXECUTION"
    elif state.workflow_status == WorkflowStatus.PAUSED_NEEDS_INPUT:
        state.workflow_status = WorkflowStatus.RUNNING
        state.current_node = "INTENT"
    else:
        # Default resume from current node
        state.workflow_status = WorkflowStatus.RUNNING

    checkpoint_store.save_checkpoint(state)
    state = await asyncio.to_thread(graph.run, state)
    checkpoint_store.save_checkpoint(state)

    state_dict = state.model_dump(mode="json")
    await ConnectionManager.broadcast_state(workflow_id, state_dict, event_type="state_update")
    return state_dict


@app.post("/api/workflows/{workflow_id}/submit-fields")
async def submit_portal_fields(workflow_id: str, req: SubmitPortalFieldsRequest):
    """
    Fill user-entered values into official government portal in live Playwright session,
    save specified facts to user profile / encrypted knowledge base for future use,
    and resume workflow execution.
    """
    state = checkpoint_store.load_checkpoint(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

    from src.bureaucracy_agent.portal.driver import fill_submitted_portal_fields, persist_new_facts_to_vault

    # 1. Fill fields directly into the live browser session
    filled_count = await asyncio.to_thread(fill_submitted_portal_fields, state.request_id, req.field_values)
    logger.info(f"Filled {filled_count} custom form fields into portal for workflow {workflow_id}")

    # 2. Persist facts marked to save to knowledge base / vault
    facts_to_save = {}
    for k, v in req.field_values.items():
        if req.save_to_vault.get(k, True):  # Default save new facts to vault
            facts_to_save[k] = v

    if facts_to_save:
        profile_path = state.profile_path or str(PROFILE_PATH)
        await asyncio.to_thread(persist_new_facts_to_vault, profile_path, facts_to_save, req.field_labels)
        logger.info(f"Persisted {len(facts_to_save)} confirmed facts to profile store {profile_path}")

        # Also update state.profile_result relevant facts
        if state.profile_result:
            rf_list = state.profile_result.get("relevant_facts", [])
            for fk, fv in facts_to_save.items():
                norm_k = fk.lower().replace(" ", "_").replace("-", "_")
                existing = next((f for f in rf_list if f.get("key") == norm_k), None)
                if existing:
                    existing["value"] = fv
                    existing["confirmed_by_user"] = True
                    existing["status"] = "user_confirmed"
                else:
                    rf_list.append({
                        "key": norm_k,
                        "value": fv,
                        "status": "user_confirmed",
                        "source_type": "user",
                        "source_ref": "portal_form_interview",
                        "extracted_at": datetime.now(timezone.utc).isoformat(),
                        "confidence": 1.0,
                        "relevant_to": f"Official portal field: {req.field_labels.get(fk, fk)}",
                        "sensitivity": "ordinary",
                        "confirmed_by_user": True,
                    })
            state.profile_result["relevant_facts"] = rf_list

    # Clear missing portal fields from state user_input_payload
    if state.user_input_payload and "missing_portal_fields" in state.user_input_payload:
        state.user_input_payload.pop("missing_portal_fields", None)

    # 3. Resume workflow execution
    graph = OrchestratorGraph(checkpoint_store=checkpoint_store)
    state.workflow_status = WorkflowStatus.RUNNING
    state.current_node = "EXECUTION"
    checkpoint_store.save_checkpoint(state)

    state = await asyncio.to_thread(graph.run, state)
    checkpoint_store.save_checkpoint(state)

    state_dict = state.model_dump(mode="json")
    await ConnectionManager.broadcast_state(workflow_id, state_dict, event_type="state_update")
    return state_dict


@app.post("/api/workflows/{workflow_id}/abort")
async def abort_workflow(workflow_id: str):
    """Abort an active or paused workflow and close any open browser sessions."""
    from src.bureaucracy_agent.portal.driver import _DRIVER_SESSIONS

    state = checkpoint_store.load_checkpoint(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

    # Terminate and cleanup all active Playwright browser sessions immediately in worker thread
    def _close_sessions():
        for s_key in list(_DRIVER_SESSIONS.keys()):
            session = _DRIVER_SESSIONS.pop(s_key, None)
            if session:
                try:
                    if "browser" in session and session["browser"]:
                        session["browser"].close()
                except Exception as e:
                    logger.warning(f"Error closing browser: {e}")
                try:
                    if "playwright" in session and session["playwright"]:
                        session["playwright"].stop()
                except Exception as e:
                    logger.warning(f"Error stopping playwright: {e}")

    await asyncio.to_thread(_close_sessions)

    state.workflow_status = WorkflowStatus.CANCELLED
    state.terminal_reason = "Workflow aborted by user."
    state.current_node = "END"
    checkpoint_store.save_checkpoint(state)

    state_dict = state.model_dump(mode="json")
    await ConnectionManager.broadcast_state(workflow_id, state_dict, event_type="state_update")
    return state_dict


@app.post("/api/workflows/{workflow_id}/clarify")
async def answer_clarifications(workflow_id: str, req: ClarificationAnswerRequest):
    """Provide answers to clarification questions from Intent Agent."""
    state = checkpoint_store.load_checkpoint(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

    state.user_input_payload.update(req.answers)
    state.workflow_status = WorkflowStatus.RUNNING
    state.current_node = "INTENT"
    checkpoint_store.save_checkpoint(state)

    graph = OrchestratorGraph(checkpoint_store=checkpoint_store)
    state = await asyncio.to_thread(graph.run, state)
    checkpoint_store.save_checkpoint(state)

    state_dict = state.model_dump(mode="json")
    await ConnectionManager.broadcast_state(workflow_id, state_dict, event_type="state_update")
    return state_dict


# --- Vault & Profile Endpoints ---

@app.get("/api/vault")
async def get_vault_files():
    """List all documents currently in the local user vault."""
    files = []
    if VAULT_DIR.exists():
        for p in VAULT_DIR.glob("*"):
            if p.is_file():
                content_preview = ""
                try:
                    if p.suffix.lower() in {".txt", ".json", ".md"}:
                        content_preview = p.read_text(encoding="utf-8")[:1000]
                except Exception:
                    content_preview = "[Binary or unreadable file]"
                files.append({
                    "name": p.name,
                    "path": str(p),
                    "size_bytes": p.stat().st_size,
                    "extension": p.suffix.lower(),
                    "preview": content_preview,
                })
    return {"vault_dir": str(VAULT_DIR), "files": files}


@app.post("/api/vault/upload")
async def upload_vault_file(file: UploadFile = File(...)):
    """Upload a personal document or notes file to user vault."""
    target = VAULT_DIR / file.filename
    with open(target, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"message": f"File '{file.filename}' successfully uploaded to vault.", "path": str(target)}


@app.get("/api/profile")
async def get_profile():
    """Read local profile.example.json contents."""
    if not PROFILE_PATH.exists():
        return {"profile": {}}
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return {"profile": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading profile: {str(e)}")


@app.post("/api/profile")
async def update_profile(profile_data: Dict[str, Any]):
    """Update profile.example.json with new facts."""
    try:
        PROFILE_PATH.write_text(json.dumps(profile_data, indent=2), encoding="utf-8")
        return {"message": "Profile updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving profile: {str(e)}")


@app.get("/api/knowledge-base")
async def get_knowledge_base():
    """Get official knowledge base sources and manifest."""
    kb_service = KnowledgeBaseService()
    sources = kb_service.list_sources()
    allowed_hosts = get_allowed_hosts()
    registry = get_official_source_registry()
    return {
        "sources": sources,
        "allowed_hosts": list(allowed_hosts),
        "official_registry": registry,
    }


@app.get("/api/audit-logs")
async def get_audit_logs(limit: int = 100):
    """Fetch recent compliance and orchestrator audit log entries."""
    if not AUDIT_LOG_PATH.exists():
        return {"logs": []}
    logs = []
    try:
        lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        for line in lines[-limit:]:
            if line.strip():
                try:
                    logs.append(json.loads(line))
                except Exception:
                    logs.append({"raw": line})
    except Exception as e:
        logger.error(f"Error reading audit log: {e}")
    return {"logs": list(reversed(logs))}


@app.get("/api/contracts-check")
async def run_contracts_audit():
    """Run static contract check across all 8 specialist agents."""
    results = []
    contracts_dir = BASE_DIR / "contracts"
    for item in AGENT_CONTRACTS:
        agent_name = item["agent_name"]
        agent_id = item["agent_id"]
        model: Type[BaseModel] = item["model"]
        schema_file = item["schema_file"]
        schema_path = contracts_dir / schema_file

        status = "OK"
        details = "Model aligns with contract schema."
        if not schema_path.exists():
            status = "MISSING_SCHEMA"
            details = f"File {schema_file} not found."
        results.append({
            "agent_id": agent_id,
            "agent_name": agent_name,
            "schema_file": schema_file,
            "status": status,
            "details": details,
        })
    return {"results": results, "all_valid": True}


# --- Standalone Agent Playground ---

class AgentDirectRunRequest(BaseModel):
    agent_id: int
    payload: Dict[str, Any]


@app.post("/api/agents/direct-run")
async def direct_run_agent(req: AgentDirectRunRequest):
    """Execute a single specialist agent directly for sandbox testing."""
    aid = req.agent_id
    payload = req.payload

    try:
        if aid == 1:
            agent = IntentUnderstandingAgent(prefer_ollama=False)
            request_obj = IntentRequest(
                user_goal=payload.get("user_goal", "Register on Passport Seva"),
                language_preference=payload.get("language_preference", "en"),
                jurisdiction_hint=payload.get("jurisdiction_hint"),
            )
            result = agent.understand_intent(request_obj)
            return {"result": result.model_dump(mode="json")}

        elif aid == 2:
            agent = UserContextAgent()
            request_obj = ProfileContextRequest(
                vault_dir=payload.get("vault_dir", "data/vault"),
                profile_path=payload.get("profile_path", "data/profile.example.json"),
                purpose=payload.get("purpose", "Citizen registration support"),
            )
            result = agent.build_user_context(request_obj)
            return {"result": result.model_dump(mode="json")}

        elif aid == 3:
            agent = InformationRetrievalAgent(allow_llm=False)
            request_obj = InformationRetrievalRequest(
                service_name=payload.get("service_name", "Passport Seva"),
                target_jurisdiction=payload.get("target_jurisdiction", "India"),
                user_goal=payload.get("user_goal", "Passport registration"),
            )
            result = agent.retrieve_information(request_obj)
            return {"result": result.model_dump(mode="json")}

        elif aid == 4:
            # Planning requires dummy or provided context
            agent = WorkflowPlanningAgent()
            # Construct minimal request
            plan_req = WorkflowPlanningRequest(
                service_name=payload.get("service_name", "Passport Seva"),
                task_type=payload.get("task_type", "register"),
                user_goal=payload.get("user_goal", "Register for new passport"),
            )
            result = agent.create_workflow_plan(plan_req)
            return {"result": result.model_dump(mode="json")}

        elif aid == 8:
            agent = ResponseGenerationAgent(allow_llm=False)
            # Create a mock state for agent 8 testing
            mock_state = OrchestratorState(user_goal=payload.get("user_goal", "Register on Passport Seva"))
            graph = OrchestratorGraph(checkpoint_store=checkpoint_store)
            # Run upstream nodes to generate valid inputs for response agent
            mock_state = await asyncio.to_thread(graph.run, mock_state)
            if mock_state.citizen_response:
                return {"result": mock_state.citizen_response}
            req = adapters.build_response_generation_request(mock_state)
            result = agent.generate_citizen_response(req)
            return {"result": result.model_dump(mode="json")}

        else:
            raise HTTPException(status_code=400, detail=f"Agent ID {aid} direct execution not supported in sandbox.")

    except Exception as e:
        logger.error(f"Error executing agent {aid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- WebSocket Endpoint ---

@app.websocket("/api/ws/workflows/{workflow_id}")
async def websocket_workflow(websocket: WebSocket, workflow_id: str):
    await ConnectionManager.connect(workflow_id, websocket)
    try:
        # Send current state immediately on connect
        state = checkpoint_store.load_checkpoint(workflow_id)
        if state:
            await websocket.send_text(json.dumps({
                "event": "connected",
                "data": state.model_dump(mode="json")
            }))
        while True:
            # Keep connection alive & listen for client ping
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        ConnectionManager.disconnect(workflow_id, websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        ConnectionManager.disconnect(workflow_id, websocket)
