import React from 'react';
import {
  Brain,
  UserCheck,
  Search,
  FileCode2,
  ShieldCheck,
  Globe2,
  FileCheck2,
  Activity,
  Award,
  Check,
  PauseCircle,
  AlertTriangle,
  XOctagon,
  CheckCircle2,
} from 'lucide-react';
import { WorkflowStatus } from '../types';

interface GraphVisualizerProps {
  currentNode: string;
  workflowStatus: WorkflowStatus;
}

interface GraphStepDef {
  id: string;
  stepNum: string;
  label: string;
  shortDesc: string;
  matchNodes: string[];
  icon: React.ComponentType<{ size: number; strokeWidth?: number }>;
}

// Exact 9 stages matching the backend state machine graph (graph.py)
const GRAPH_STAGES: GraphStepDef[] = [
  {
    id: 'intent',
    stepNum: '01',
    label: 'Request Analysis',
    shortDesc: 'Intent & Entity Extraction',
    matchNodes: ['START', 'INTENT', 'PAUSED_NEEDS_INPUT'],
    icon: Brain,
  },
  {
    id: 'user_context',
    stepNum: '02',
    label: 'Citizen Context',
    shortDesc: 'Vault Fact Verification',
    matchNodes: ['USER_CONTEXT', 'PAUSED_FACT_CONSENT'],
    icon: UserCheck,
  },
  {
    id: 'retrieval',
    stepNum: '03',
    label: 'Statutory Retrieval',
    shortDesc: 'Portal Rules & Guidelines',
    matchNodes: ['RETRIEVAL'],
    icon: Search,
  },
  {
    id: 'planning',
    stepNum: '04',
    label: 'Workflow Planning',
    shortDesc: 'Deterministic Action Plan',
    matchNodes: ['PLANNING'],
    icon: FileCode2,
  },
  {
    id: 'compliance_pre',
    stepNum: '05',
    label: 'Safety Compliance',
    shortDesc: 'Zero-Trust Gate Check',
    matchNodes: ['COMPLIANCE_PRE', 'PAUSED_NEEDS_AUTHORIZATION', 'STOP_BLOCKED'],
    icon: ShieldCheck,
  },
  {
    id: 'execution',
    stepNum: '06',
    label: 'Portal Execution',
    shortDesc: 'Assisted Browser Automation',
    matchNodes: ['EXECUTION', 'PAUSED_CAPTCHA', 'PAUSED_PAYMENT'],
    icon: Globe2,
  },
  {
    id: 'compliance_post',
    stepNum: '07',
    label: 'Evidence Audit',
    shortDesc: 'Receipt & Proof Verification',
    matchNodes: ['COMPLIANCE_POST'],
    icon: FileCheck2,
  },
  {
    id: 'monitoring',
    stepNum: '08',
    label: 'Status Tracking',
    shortDesc: 'Lifecycle Schedule',
    matchNodes: ['MONITORING'],
    icon: Activity,
  },
  {
    id: 'response',
    stepNum: '09',
    label: 'Citizen Guidance',
    shortDesc: 'Official Reference Summary',
    matchNodes: ['RESPONSE', 'END'],
    icon: Award,
  },
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

  let currentStageIdx = GRAPH_STAGES.findIndex((s) => s.matchNodes.includes(currentNode));
  if (currentStageIdx === -1) {
    if (isCompleted) currentStageIdx = GRAPH_STAGES.length - 1;
    else currentStageIdx = 0;
  }

  const progressPercent = isCompleted
    ? 100
    : Math.round(((currentStageIdx + (isPaused ? 0.5 : 0.8)) / GRAPH_STAGES.length) * 100);

  return (
    <div
      className="card"
      style={{
        margin: '0 20px 24px 20px',
        padding: '20px 24px',
        borderRadius: 'var(--radius-md)',
        backgroundColor: 'var(--bg-surface)',
      }}
    >
      {/* Header bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '16px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span className="section-label">State Machine Execution</span>
            <span className="stamped-slip" style={{ fontSize: '0.72rem', padding: '2px 6px' }}>
              9 Statutory Stages
            </span>
          </div>
          <h3
            style={{
              fontSize: '1.05rem',
              fontWeight: 600,
              color: 'var(--text-primary)',
              margin: 0,
            }}
          >
            Workflow Pipeline Stage: <span style={{ color: 'var(--accent-primary)' }}>{GRAPH_STAGES[currentStageIdx]?.label}</span>
          </h3>
        </div>

        {/* Current status badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isPaused && (
            <span className="badge badge-warning" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
              <PauseCircle size={14} strokeWidth={1.75} />
              Action Required: {workflowStatus.replace('PAUSED_', '').replace(/_/g, ' ')}
            </span>
          )}
          {isBlocked && (
            <span className="badge badge-danger" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
              <AlertTriangle size={14} strokeWidth={1.75} /> Gate Blocked
            </span>
          )}
          {isCancelled && (
            <span className="badge badge-danger" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
              <XOctagon size={14} strokeWidth={1.75} /> Workflow Aborted
            </span>
          )}
          {isCompleted && (
            <span className="badge badge-verified" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
              <CheckCircle2 size={14} strokeWidth={1.75} /> All Stages Confirmed
            </span>
          )}
          {isFailed && (
            <span className="badge badge-danger" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
              <AlertTriangle size={14} strokeWidth={1.75} /> Execution Failed
            </span>
          )}
          {!isPaused && !isBlocked && !isCompleted && !isFailed && !isCancelled && (
            <span className="badge badge-accent" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
              <span className="status-dot status-dot-blue" style={{ marginRight: '2px' }} />
              Stage {currentStageIdx + 1} of 9 in Progress
            </span>
          )}
        </div>
      </div>

      {/* Progress Bar Rule */}
      <div
        style={{
          width: '100%',
          height: '4px',
          backgroundColor: 'var(--border-subtle)',
          borderRadius: '2px',
          marginBottom: '20px',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${progressPercent}%`,
            backgroundColor: isCompleted ? 'var(--state-verified-icon)' : 'var(--accent-primary)',
            transition: 'width 0.35s ease',
          }}
        />
      </div>

      {/* Stepper Horizontal Scroll Container */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(9, minmax(110px, 1fr))',
          gap: '8px',
          overflowX: 'auto',
          paddingBottom: '6px',
        }}
      >
        {GRAPH_STAGES.map((stage, idx) => {
          const isStageCompleted = isCompleted || idx < currentStageIdx;
          const isStageActive = idx === currentStageIdx && !isCompleted;
          const isStageUpcoming = idx > currentStageIdx && !isCompleted;

          const IconComponent = stage.icon;

          let bg = 'var(--bg-stamped-slip)';
          let borderColor = 'var(--border-subtle)';
          let textColor = 'var(--text-muted)';
          let iconColor = 'var(--text-muted)';

          if (isStageCompleted) {
            bg = 'var(--accent-primary)';
            borderColor = 'var(--accent-primary)';
            textColor = '#ffffff';
            iconColor = '#ffffff';
          } else if (isStageActive) {
            bg = isPaused ? 'var(--state-warning-bg)' : 'var(--accent-subtle)';
            borderColor = isPaused ? 'var(--state-warning-border)' : 'var(--accent-border)';
            textColor = isPaused ? 'var(--state-warning-text)' : 'var(--accent-primary)';
            iconColor = isPaused ? 'var(--state-warning-icon)' : 'var(--accent-primary)';
          }

          return (
            <div
              key={stage.id}
              style={{
                borderRadius: 'var(--radius-sm)',
                border: `1px solid ${borderColor}`,
                padding: '10px 8px',
                backgroundColor: isStageCompleted ? '#0f3a5a' : isStageActive ? (isPaused ? '#fef3c7' : '#e4ecf3') : '#f4efe6',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                minHeight: '84px',
                transition: 'all 0.15s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.68rem',
                    fontWeight: 600,
                    color: isStageCompleted ? '#dce6ef' : textColor,
                  }}
                >
                  {stage.stepNum}
                </span>

                <div
                  style={{
                    width: '20px',
                    height: '20px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: isStageCompleted ? 'rgba(255,255,255,0.2)' : 'transparent',
                    color: iconColor,
                  }}
                >
                  {isStageCompleted ? (
                    <Check size={12} strokeWidth={2.5} />
                  ) : (
                    <IconComponent size={13} strokeWidth={1.75} />
                  )}
                </div>
              </div>

              <div>
                <div
                  style={{
                    fontSize: '0.74rem',
                    fontWeight: isStageActive ? 700 : 600,
                    color: isStageCompleted ? '#ffffff' : isStageActive ? (isPaused ? '#78350f' : '#0f3a5a') : 'var(--text-primary)',
                    lineHeight: 1.25,
                    marginBottom: '2px',
                  }}
                >
                  {stage.label}
                </div>
                <div
                  style={{
                    fontSize: '0.66rem',
                    color: isStageCompleted ? '#b8c8d6' : 'var(--text-muted)',
                    lineHeight: 1.2,
                  }}
                >
                  {stage.shortDesc}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
