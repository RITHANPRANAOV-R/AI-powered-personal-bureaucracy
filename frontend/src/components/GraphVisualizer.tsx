import React from 'react';
import {
  Brain,
  UserCheck,
  Search,
  ShieldCheck,
  Terminal,
  CheckCircle2,
  PauseCircle,
  AlertTriangle,
  XOctagon,
} from 'lucide-react';
import { WorkflowStatus } from '../types';

interface GraphVisualizerProps {
  currentNode: string;
  workflowStatus: WorkflowStatus;
}

interface StepDef {
  id: string;
  label: string;
  description: string;
  matchNodes: string[];
  icon: React.ComponentType<{ size: number; color?: string }>;
}

const USER_STEPS: StepDef[] = [
  { id: 'intent', label: '1. Request Analysis', description: 'Intent & Entity Extraction', matchNodes: ['START', 'INTENT', 'PAUSED_NEEDS_INPUT'], icon: Brain },
  { id: 'profile', label: '2. Citizen Profile', description: 'Vault Fact Verification', matchNodes: ['USER_CONTEXT', 'PAUSED_FACT_CONSENT'], icon: UserCheck },
  { id: 'retrieval', label: '3. Official Rules', description: 'Gov Portal Knowledge', matchNodes: ['RETRIEVAL', 'PLANNING'], icon: Search },
  { id: 'compliance', label: '4. Safety & Authorization', description: 'Zero-Trust Gate Check', matchNodes: ['COMPLIANCE_PRE', 'PAUSED_NEEDS_AUTHORIZATION', 'STOP_BLOCKED'], icon: ShieldCheck },
  { id: 'execution', label: '5. Browser Automation', description: 'Assisted Portal Execution', matchNodes: ['EXECUTION', 'PAUSED_CAPTCHA', 'PAUSED_PAYMENT', 'COMPLIANCE_POST', 'MONITORING'], icon: Terminal },
  { id: 'response', label: '6. Official Confirmation', description: 'Citizen Reference Report', matchNodes: ['RESPONSE', 'END'], icon: CheckCircle2 },
];

export const GraphVisualizer: React.FC<GraphVisualizerProps> = ({
  currentNode,
  workflowStatus,
}) => {
  const isPaused = workflowStatus.startsWith('PAUSED_');
  const isBlocked = workflowStatus === 'STOP_BLOCKED';
  const isFailed = workflowStatus === 'FAILED';
  const isCancelled = workflowStatus === 'CANCELLED';
  const isCompleted = workflowStatus === 'COMPLETED' || currentNode === 'END';

  // Find step index matching current node
  let currentStepIdx = USER_STEPS.findIndex((s) => s.matchNodes.includes(currentNode));
  if (currentStepIdx === -1) {
    if (isCompleted) currentStepIdx = 5;
    else currentStepIdx = 0;
  }

  return (
    <div className="glass-panel" style={{ padding: '20px 24px', margin: '0 20px 20px 20px' }}>
      
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            Autonomous Execution Progress
          </h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Real-Time Multi-Agent Pipeline
          </span>
        </div>

        {/* Current status pill */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isPaused && (
            <span className="badge badge-amber" style={{ animation: 'pulse-glow 1.5s infinite', padding: '6px 12px' }}>
              <PauseCircle size={14} /> Action Needed: {workflowStatus.replace('PAUSED_', '').replace('_', ' ')}
            </span>
          )}
          {isBlocked && (
            <span className="badge badge-rose" style={{ padding: '6px 12px' }}>
              <AlertTriangle size={14} /> Gate Blocked
            </span>
          )}
          {isCancelled && (
            <span className="badge badge-rose" style={{ padding: '6px 12px' }}>
              <XOctagon size={14} /> Workflow Aborted
            </span>
          )}
          {isCompleted && (
            <span className="badge badge-emerald" style={{ padding: '6px 12px' }}>
              <CheckCircle2 size={14} /> Application Completed
            </span>
          )}
          {isFailed && (
            <span className="badge badge-rose" style={{ padding: '6px 12px' }}>
              <AlertTriangle size={14} /> Execution Failed
            </span>
          )}
          {!isPaused && !isBlocked && !isCompleted && !isFailed && !isCancelled && (
            <span className="badge badge-indigo" style={{ padding: '6px 12px' }}>
              <span className="pulse-dot" style={{ background: '#818cf8', width: '6px', height: '6px' }} />
              Executing Stage {currentStepIdx + 1}/6
            </span>
          )}
        </div>
      </div>

      {/* Stepper Progress Bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px' }}>
        {USER_STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isActive = idx === currentStepIdx;
          const isPassed = currentStepIdx > idx || isCompleted;

          let borderStyle = '1px solid var(--border-subtle)';
          let bgStyle = 'rgba(255, 255, 255, 0.02)';
          let textColor = 'var(--text-muted)';
          let iconColor = 'var(--text-muted)';

          if (isPassed && !isActive) {
            borderStyle = '1px solid rgba(16, 185, 129, 0.4)';
            bgStyle = 'rgba(16, 185, 129, 0.08)';
            textColor = '#cbd5e1';
            iconColor = '#10b981';
          } else if (isActive) {
            if (isPaused) {
              borderStyle = '1px solid #f59e0b';
              bgStyle = 'rgba(245, 158, 11, 0.15)';
              textColor = '#fef3c7';
              iconColor = '#fbbf24';
            } else if (isCancelled || isFailed || isBlocked) {
              borderStyle = '1px solid #f43f5e';
              bgStyle = 'rgba(244, 63, 94, 0.15)';
              textColor = '#ffe4e6';
              iconColor = '#fb7185';
            } else {
              borderStyle = '1px solid #6366f1';
              bgStyle = 'linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(6, 182, 212, 0.15))';
              textColor = '#ffffff';
              iconColor = '#67e8f9';
            }
          }

          return (
            <div
              key={step.id}
              style={{
                padding: '12px 14px',
                borderRadius: '12px',
                background: bgStyle,
                border: borderStyle,
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                transition: 'all 0.2s ease',
              }}
            >
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <Icon size={18} color={iconColor} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '0.82rem', fontWeight: 700, color: textColor, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {step.label}
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {step.description}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
