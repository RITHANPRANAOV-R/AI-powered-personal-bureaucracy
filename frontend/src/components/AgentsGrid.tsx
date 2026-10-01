import React from 'react';
import {
  Brain,
  UserCheck,
  Search,
  GitPullRequest,
  ShieldCheck,
  Terminal,
  Clock,
  MessageSquare,
  Play,
  FileCode,
  Cpu,
  ArrowRight,
} from 'lucide-react';
import { AgentInfo } from '../types';

interface AgentsGridProps {
  agents: AgentInfo[];
  onOpenSandbox: (agent: AgentInfo) => void;
  activeAgentId?: number;
}

const AGENT_ICONS: Record<number, React.ComponentType<{ size: number; color?: string }>> = {
  1: Brain,
  2: UserCheck,
  3: Search,
  4: GitPullRequest,
  5: ShieldCheck,
  6: Terminal,
  7: Clock,
  8: MessageSquare,
};

export const AgentsGrid: React.FC<AgentsGridProps> = ({
  agents,
  onOpenSandbox,
  activeAgentId,
}) => {
  return (
    <div style={{ margin: '0 20px 20px 20px' }}>
      
      {/* Header */}
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
          8 Specialist Agents Architecture
        </h2>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Each agent operates with isolated boundaries, strict Pydantic JSON contracts, and deterministic state transitions.
        </p>
      </div>

      {/* Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
        {agents.map((agent) => {
          const Icon = AGENT_ICONS[agent.id] || Brain;
          const isActive = activeAgentId === agent.id;

          return (
            <div
              key={agent.id}
              className="glass-panel"
              style={{
                padding: '20px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                border: isActive ? '1px solid #6366f1' : '1px solid var(--border-subtle)',
                boxShadow: isActive ? '0 0 20px rgba(99, 102, 241, 0.3)' : 'var(--shadow-sm)',
              }}
            >
              <div>
                {/* Top badges */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div
                      style={{
                        width: '36px',
                        height: '36px',
                        borderRadius: '10px',
                        background: 'rgba(99, 102, 241, 0.15)',
                        border: '1px solid rgba(99, 102, 241, 0.3)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <Icon size={18} color="#818cf8" />
                    </div>
                    <div>
                      <span className="badge badge-indigo" style={{ fontSize: '0.65rem' }}>
                        Agent {agent.id}
                      </span>
                    </div>
                  </div>

                  <span className="badge badge-cyan" style={{ fontSize: '0.65rem' }}>
                    {agent.role}
                  </span>
                </div>

                {/* Name & Description */}
                <h3 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '6px' }}>
                  {agent.name}
                </h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: '16px' }}>
                  {agent.description}
                </p>

                {/* Contract & Runtime Specs */}
                <div style={{ background: 'rgba(5, 7, 12, 0.5)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '10px 12px', marginBottom: '14px', fontSize: '0.75rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px', color: 'var(--text-muted)' }}>
                    <FileCode size={12} color="#38bdf8" />
                    <span>Contract: <strong style={{ color: '#e2e8f0' }}>{agent.contract}</strong></span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)' }}>
                    <Cpu size={12} color="#a855f7" />
                    <span>Runtime: <strong style={{ color: '#e2e8f0' }}>{agent.runtime}</strong></span>
                  </div>
                </div>

                {/* Inputs & Outputs Tags */}
                <div style={{ marginBottom: '14px' }}>
                  <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                    Output Schema Attributes
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {agent.outputs.map((out) => (
                      <span
                        key={out}
                        style={{
                          background: 'rgba(255, 255, 255, 0.04)',
                          border: '1px solid var(--border-subtle)',
                          padding: '2px 8px',
                          borderRadius: '6px',
                          fontSize: '0.7rem',
                          color: '#94a3b8',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        {out}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Bottom Sandbox Launch */}
              <button
                onClick={() => onOpenSandbox(agent)}
                className="btn-secondary"
                style={{ width: '100%', fontSize: '0.8rem', padding: '8px 12px', justifyContent: 'center' }}
              >
                <Play size={13} color="#38bdf8" />
                Run Sandbox Test
              </button>
            </div>
          );
        })}
      </div>

    </div>
  );
};
