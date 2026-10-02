export type WorkflowStatus =
  | 'RUNNING'
  | 'PAUSED_NEEDS_INPUT'
  | 'PAUSED_FACT_CONSENT'
  | 'PAUSED_NEEDS_AUTHORIZATION'
  | 'PAUSED_CAPTCHA'
  | 'PAUSED_PAYMENT'
  | 'PAUSED_UNKNOWN_FIELDS'
  | 'STOP_BLOCKED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface MissingPortalField {
  key: string;
  name: string;
  id: string;
  label: string;
  type: string;
  options?: Array<{ value: string; label: string }>;
  placeholder?: string;
  is_required?: boolean;
}

export interface ProfileFact {
  key: string;
  value: string;
  source_ref: string;
  confirmed_by_user: boolean;
  sensitive: boolean;
  category?: string;
}

export interface IntentResult {
  contract_version: string;
  request_id: string;
  original_goal: string;
  service_type: string;
  task_type: string;
  confidence_score: number;
  explicit_facts: Record<string, any>;
  clarification_questions: string[];
  jurisdiction?: string;
  urgency?: string;
  routing_status: 'ready' | 'needs_clarification' | 'unable_to_classify';
}

export interface ProfileContextResult {
  contract_version: string;
  request_id: string;
  relevant_facts: ProfileFact[];
  missing_facts: string[];
  unconfirmed_facts: string[];
  consent_audit: Array<{
    fact_key: string;
    action: 'save' | 'use_once' | 'skip';
    timestamp: string;
  }>;
}

export interface EvidenceItem {
  source_name: string;
  source_url: string;
  snippet: string;
  trust_score: number;
  retrieved_at: string;
  fee_amount?: string;
  requirements?: string[];
}

export interface RetrievedEvidenceResult {
  contract_version: string;
  request_id: string;
  service_name: string;
  target_jurisdiction: string;
  official_urls: string[];
  evidence_items: EvidenceItem[];
  fee_details: Record<string, any>;
  required_documents: string[];
  trust_score_average: number;
}

export interface WorkflowStep {
  step_id: string;
  title: string;
  description: string;
  actor: 'assistant' | 'citizen' | 'official_portal';
  prerequisites: string[];
  estimated_minutes: number;
  requires_user_approval: boolean;
  approval_phrase_hint?: string;
  portal_url?: string;
  status?: string;
}

export interface WorkflowPlan {
  contract_version: string;
  request_id: string;
  service_name: string;
  task_type: string;
  steps: WorkflowStep[];
  critical_path: string[];
  estimated_total_minutes: number;
  required_user_approvals: Array<{
    step_id: string;
    required_phrase: string;
    reason: string;
  }>;
}

export interface ValidationIssue {
  severity: 'error' | 'warning' | 'info';
  category: string;
  affected_step_ids: string[];
  message: string;
  required_resolution?: string;
}

export interface ValidationResult {
  contract_version: string;
  request_id: string;
  phase: 'pre_execution' | 'post_execution';
  decision: 'approved' | 'rejected' | 'needs_consent' | 'needs_authorization';
  summary: string;
  eligible_step_ids: string[];
  blocked_step_ids: string[];
  issues: ValidationIssue[];
  required_user_approvals: Array<{
    step_id: string;
    required_phrase: string;
    reason: string;
  }>;
}

export interface ExecutionResult {
  contract_version: string;
  request_id: string;
  execution_status: 'success' | 'partial' | 'failed' | 'paused' | 'uncertain';
  executed_steps: string[];
  observed_fields: Record<string, any>;
  confirmation_id?: string;
  portal_messages: string[];
  captured_screenshots?: string[];
  timestamp: string;
}

export interface StatusEvent {
  event_id: string;
  timestamp: string;
  source_type: string;
  summary: string;
  details?: string;
}

export interface MonitoringResult {
  contract_version: string;
  request_id: string;
  monitoring_status: string;
  timeline_events: StatusEvent[];
  reminders: Array<{
    reminder_id: string;
    trigger_at: string;
    message: string;
  }>;
}

export interface CitizenResponse {
  contract_version: string;
  request_id: string;
  headline: string;
  overall_status: string;
  summary: string;
  citizen_next_step?: {
    title: string;
    description: string;
    action_type: string;
  };
  pending_actions: Array<{
    step_id: string;
    action_title: string;
    reason: string;
  }>;
  formatted_markdown: string;
}

export interface OrchestratorState {
  workflow_id: string;
  request_id: string;
  state_version: string;
  current_node: string;
  workflow_status: WorkflowStatus;
  updated_at: string;
  user_goal: string;
  language: string;
  is_demo: boolean;
  is_dry_run: boolean;
  stop_before_submit: boolean;
  vault_dir: string;
  profile_path: string;
  intent_result?: IntentResult;
  profile_result?: ProfileContextResult;
  evidence_result?: RetrievedEvidenceResult;
  workflow_plan_original?: WorkflowPlan;
  workflow_plan?: WorkflowPlan;
  user_handled_steps?: WorkflowStep[];
  validation_result?: ValidationResult;
  post_validation_result?: ValidationResult;
  execution_result?: ExecutionResult;
  monitoring_result?: MonitoringResult;
  citizen_response?: CitizenResponse;
  user_authorizations: any[];
  submission_consent: boolean;
  submission_attempted: boolean;
  confirmation_observed: boolean;
  terminal_reason: string;
  gate_reasons: string[];
  user_input_payload: Record<string, any>;
  errors: string[];
}

export interface AgentInfo {
  id: number;
  key: string;
  name: string;
  role: string;
  description: string;
  contract: string;
  schema_file: string;
  runtime: string;
  inputs: string[];
  outputs: string[];
  badge_color: string;
}

export interface WorkflowTemplate {
  id: string;
  title: string;
  category: string;
  goal: string;
  description: string;
  estimated_time: string;
  service: string;
  is_demo: boolean;
  is_dry_run: boolean;
}

export interface VaultFile {
  name: string;
  path: string;
  size_bytes: number;
  extension: string;
  preview: string;
}

export interface AuditLogEntry {
  timestamp?: string;
  event_type?: string;
  workflow_id?: string;
  agent?: string;
  node?: string;
  action?: string;
  status?: string;
  details?: any;
  hash?: string;
  raw?: string;
}
