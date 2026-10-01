import React from 'react';
import {
  ShieldCheck,
  Sparkles,
  PlusCircle,
  Activity,
  CheckCircle2,
} from 'lucide-react';

interface NavbarProps {
  systemHealth: any;
  activeWorkflowId?: string;
  onNewRequest: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  systemHealth,
  activeWorkflowId,
  onNewRequest,
}) => {
  const isOnline = systemHealth?.status === 'online';

  return (
    <header className="glass-panel" style={{ margin: '18px 24px', padding: '14px 28px', borderRadius: '18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        
        {/* Brand & Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '14px',
              background: 'linear-gradient(135deg, #6366f1 0%, #06b6d4 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 24px rgba(99, 102, 241, 0.45)',
            }}
          >
            <ShieldCheck size={26} color="#ffffff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ fontSize: '1.25rem', fontWeight: 800, letterSpacing: '-0.02em', background: 'linear-gradient(90deg, #ffffff, #e2e8f0)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                AI Personal Bureaucracy Assistant
              </h1>
              <span className="badge badge-indigo" style={{ fontSize: '0.68rem', padding: '4px 10px' }}>
                <Sparkles size={11} /> Autonomous Government Agent
              </span>
            </div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              Assisted Public Service Execution & Verification
            </p>
          </div>
        </div>

        {/* Right action & status bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 14px',
              borderRadius: '999px',
              background: isOnline ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.12)',
              border: `1px solid ${isOnline ? 'rgba(16, 185, 129, 0.35)' : 'rgba(244, 63, 94, 0.35)'}`,
            }}
          >
            <div
              className="pulse-dot"
              style={{
                background: isOnline ? '#10b981' : '#f43f5e',
                boxShadow: `0 0 10px ${isOnline ? '#10b981' : '#f43f5e'}`,
              }}
            />
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: isOnline ? '#6ee7b7' : '#fda4af' }}>
              {isOnline ? 'System Ready' : 'Connecting...'}
            </span>
          </div>

          {activeWorkflowId && (
            <button
              onClick={onNewRequest}
              className="btn-secondary"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 16px',
                fontSize: '0.84rem',
                borderRadius: '10px',
                cursor: 'pointer',
              }}
            >
              <PlusCircle size={15} color="#38bdf8" />
              New Request
            </button>
          )}
        </div>

      </div>
    </header>
  );
};
