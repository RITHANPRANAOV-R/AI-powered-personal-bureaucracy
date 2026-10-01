import React from 'react';
import { Landmark, Plus, CheckCircle2, AlertCircle } from 'lucide-react';

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
    <header
      style={{
        backgroundColor: 'var(--bg-masthead)',
        backgroundImage: `radial-gradient(circle at 100% 0%, rgba(220, 230, 239, 0.12) 0%, transparent 60%), url("data:image/svg+xml,%3Csvg width='32' height='32' viewBox='0 0 32 32' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 16 Q8 0 16 16 T32 16' fill='none' stroke='%23FFFFFF' stroke-width='0.4' stroke-opacity='0.08'/%3E%3C/svg%3E")`,
        borderBottom: '2px solid var(--border-amber-rule)',
        padding: '14px 24px',
        color: 'var(--text-on-navy)',
        boxShadow: '0 2px 8px rgba(15, 58, 90, 0.25)',
      }}
    >
      <div
        style={{
          maxWidth: '1200px',
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '14px',
        }}
      >
        {/* Brand Masthead */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '38px',
              height: '38px',
              borderRadius: 'var(--radius-xs)',
              backgroundColor: 'rgba(243, 239, 230, 0.15)',
              border: '1px solid rgba(243, 239, 230, 0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#f3efe6',
            }}
          >
            <Landmark size={20} strokeWidth={1.75} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1
                style={{
                  fontSize: '1.25rem',
                  fontWeight: 600,
                  letterSpacing: '-0.015em',
                  color: '#f3efe6',
                  margin: 0,
                  lineHeight: 1.2,
                  fontFamily: 'var(--font-serif)',
                }}
              >
                Civil Services Assistant
              </h1>
              <span
                style={{
                  fontSize: '0.68rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  fontWeight: 600,
                  backgroundColor: 'rgba(243, 239, 230, 0.12)',
                  color: '#f3efe6',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-xs)',
                  border: '1px solid rgba(243, 239, 230, 0.22)',
                }}
              >
                Official Workflow
              </span>
            </div>
            <p
              style={{
                fontSize: '0.78rem',
                color: 'var(--text-on-navy-muted)',
                margin: 0,
                marginTop: '2px',
              }}
            >
              Public Service Procedure & Statutory Execution Portal
            </p>
          </div>
        </div>

        {/* Status & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 10px',
              fontSize: '0.76rem',
              fontWeight: 500,
              borderRadius: 'var(--radius-xs)',
              backgroundColor: isOnline ? 'rgba(234, 247, 237, 0.15)' : 'rgba(254, 242, 242, 0.15)',
              border: isOnline ? '1px solid rgba(167, 227, 184, 0.35)' : '1px solid rgba(252, 165, 165, 0.35)',
              color: isOnline ? '#a7e3b8' : '#fca5a5',
            }}
          >
            {isOnline ? (
              <CheckCircle2 size={13} strokeWidth={2} style={{ color: '#86efac' }} />
            ) : (
              <AlertCircle size={13} strokeWidth={2} style={{ color: '#fca5a5' }} />
            )}
            <span>{isOnline ? 'System Ready' : 'Connecting...'}</span>
          </div>

          {activeWorkflowId && (
            <button
              onClick={onNewRequest}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                fontSize: '0.8rem',
                fontWeight: 500,
                color: '#0f3a5a',
                backgroundColor: '#f3efe6',
                border: '1px solid #d4cdc1',
                borderRadius: 'var(--radius-xs)',
                cursor: 'pointer',
                transition: 'background-color 0.15s ease',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#ffffff')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#f3efe6')}
            >
              <Plus size={14} strokeWidth={1.75} />
              <span>New Request</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
