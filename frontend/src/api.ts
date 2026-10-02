import {
  OrchestratorState,
  AgentInfo,
  WorkflowTemplate,
  VaultFile,
  AuditLogEntry,
} from './types';

const API_BASE = 'http://localhost:8000/api';
const WS_BASE = 'ws://localhost:8000/api/ws';

export async function getHealth(): Promise<any> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function getAgents(): Promise<AgentInfo[]> {
  const res = await fetch(`${API_BASE}/agents`);
  if (!res.ok) throw new Error('Failed to fetch agents');
  return res.json();
}

export async function getTemplates(): Promise<WorkflowTemplate[]> {
  const res = await fetch(`${API_BASE}/templates`);
  if (!res.ok) throw new Error('Failed to fetch templates');
  return res.json();
}

export async function startWorkflow(params: {
  user_goal: string;
  language?: string;
  is_demo?: boolean;
  is_dry_run?: boolean;
  stop_before_submit?: boolean;
  vault_dir?: string;
  profile_path?: string;
}): Promise<OrchestratorState> {
  const res = await fetch(`${API_BASE}/workflows/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_goal: params.user_goal,
      language: params.language || 'en',
      is_demo: params.is_demo !== undefined ? params.is_demo : true,
      is_dry_run: params.is_dry_run !== undefined ? params.is_dry_run : true,
      stop_before_submit: params.stop_before_submit !== undefined ? params.stop_before_submit : true,
      vault_dir: params.vault_dir || 'data/vault',
      profile_path: params.profile_path || 'data/profile.example.json',
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to start workflow' }));
    throw new Error(err.detail || 'Failed to start workflow');
  }
  return res.json();
}

export async function getWorkflows(): Promise<{ checkpoints: any[] }> {
  const res = await fetch(`${API_BASE}/workflows`);
  if (!res.ok) throw new Error('Failed to fetch checkpoints');
  return res.json();
}

export async function getWorkflow(workflowId: string): Promise<OrchestratorState> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}`);
  if (!res.ok) throw new Error('Failed to fetch workflow');
  return res.json();
}

export async function submitFactConsent(
  workflowId: string,
  decisions: Record<string, 'save' | 'use_once' | 'skip'>,
  answers: Record<string, string> = {}
): Promise<OrchestratorState> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}/consent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decisions, answers }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Consent submission failed' }));
    throw new Error(err.detail || 'Consent submission failed');
  }
  return res.json();
}

export async function submitAuthorization(
  workflowId: string,
  authorizationPhrase: string
): Promise<OrchestratorState> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}/authorize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ authorization_phrase: authorizationPhrase }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Authorization submission failed' }));
    throw new Error(err.detail || 'Authorization submission failed');
  }
  return res.json();
}

export async function resumePausedWorkflow(workflowId: string): Promise<OrchestratorState> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}/resume-pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Resume failed' }));
    throw new Error(err.detail || 'Resume failed');
  }
  return res.json();
}

export async function abortWorkflow(workflowId: string): Promise<OrchestratorState> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}/abort`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Abort workflow failed' }));
    throw new Error(err.detail || 'Abort workflow failed');
  }
  return res.json();
}

export async function submitPortalFields(
  workflowId: string,
  fieldValues: Record<string, string>,
  fieldLabels: Record<string, string> = {},
  saveToVault: Record<string, boolean> = {}
): Promise<OrchestratorState> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}/submit-fields`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      field_values: fieldValues,
      field_labels: fieldLabels,
      save_to_vault: saveToVault,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fill fields in portal' }));
    throw new Error(err.detail || 'Failed to fill fields in portal');
  }
  return res.json();
}

export async function answerClarifications(
  workflowId: string,
  answers: Record<string, string>
): Promise<OrchestratorState> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}/clarify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to submit clarification answers' }));
    throw new Error(err.detail || 'Failed to submit clarification answers');
  }
  return res.json();
}

export async function getVaultFiles(): Promise<{ vault_dir: string; files: VaultFile[] }> {
  const res = await fetch(`${API_BASE}/vault`);
  if (!res.ok) throw new Error('Failed to fetch vault files');
  return res.json();
}

export async function uploadVaultFile(file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/vault/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error('Failed to upload file to vault');
  return res.json();
}

export async function getProfile(): Promise<{ profile: any }> {
  const res = await fetch(`${API_BASE}/profile`);
  if (!res.ok) throw new Error('Failed to fetch profile');
  return res.json();
}

export async function updateProfile(profileData: any): Promise<any> {
  const res = await fetch(`${API_BASE}/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profileData),
  });
  if (!res.ok) throw new Error('Failed to update profile');
  return res.json();
}

export async function getKnowledgeBase(): Promise<any> {
  const res = await fetch(`${API_BASE}/knowledge-base`);
  if (!res.ok) throw new Error('Failed to fetch knowledge base');
  return res.json();
}

export async function getAuditLogs(limit: number = 100): Promise<{ logs: AuditLogEntry[] }> {
  const res = await fetch(`${API_BASE}/audit-logs?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch audit logs');
  return res.json();
}

export async function runContractsCheck(): Promise<any> {
  const res = await fetch(`${API_BASE}/contracts-check`);
  if (!res.ok) throw new Error('Failed to run contracts check');
  return res.json();
}

export async function directRunAgent(agentId: number, payload: any): Promise<any> {
  const res = await fetch(`${API_BASE}/agents/direct-run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, payload }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Direct run failed' }));
    throw new Error(err.detail || 'Direct run failed');
  }
  return res.json();
}

export function createWorkflowWebSocket(
  workflowId: string,
  onMessage: (event: string, data: any) => void,
  onError?: (err: any) => void
): () => void {
  const ws = new WebSocket(`${WS_BASE}/workflows/${workflowId}`);

  ws.onopen = () => {
    // Send periodic ping to keep socket alive
    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 20000);
    (ws as any)._pingInterval = interval;
  };

  ws.onmessage = (msg) => {
    try {
      const parsed = JSON.parse(msg.data);
      onMessage(parsed.event, parsed.data);
    } catch (e) {
      console.warn('WS parse error', e);
    }
  };

  ws.onerror = (err) => {
    if (onError) onError(err);
  };

  return () => {
    if ((ws as any)._pingInterval) {
      clearInterval((ws as any)._pingInterval);
    }
    ws.close();
  };
}
