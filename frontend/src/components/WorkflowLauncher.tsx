import React, { useState } from 'react';
import {
  ArrowRight,
  Sliders,
  ShieldCheck,
  FileText,
  Loader2,
  Sparkles,
  HelpCircle,
} from 'lucide-react';
import { WorkflowTemplate } from '../types';

interface WorkflowLauncherProps {
  templates?: WorkflowTemplate[];
  onStartWorkflow: (params: {
    user_goal: string;
    language: string;
    is_demo: boolean;
    is_dry_run: boolean;
    stop_before_submit: boolean;
  }) => void;
  isLoading: boolean;
}

const POPULAR_PROMPTS = [
  "Submit an RTI Online request to Ministry of External Affairs regarding passport dispatch timeline.",
  "Track status of my Aadhaar update request with SRN S102938475610.",
  "How do I update my permanent address in Aadhaar using my electricity bill?",
  "File a consumer grievance on National Consumer Helpline for delayed service delivery.",
  "Check eligibility and document requirements for applying for a fresh Tatkaal Passport.",
];

export const WorkflowLauncher: React.FC<WorkflowLauncherProps> = ({
  onStartWorkflow,
  isLoading,
}) => {
  const [goal, setGoal] = useState('');
  const [language, setLanguage] = useState('en');
  const [isDryRun, setIsDryRun] = useState(false);
  const [stopBeforeSubmit, setStopBeforeSubmit] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim() || isLoading) return;
    onStartWorkflow({
      user_goal: goal.trim(),
      language,
      is_demo: false,
      is_dry_run: isDryRun,
      stop_before_submit: stopBeforeSubmit,
    });
  };

  const handleSelectPrompt = (promptText: string) => {
    setGoal(promptText);
  };

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-hero-band)',
        backgroundImage: `radial-gradient(ellipse at 85% 20%, rgba(15, 58, 90, 0.06) 0%, transparent 60%), url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' stroke='%230F3A5A' stroke-width='0.5' stroke-opacity='0.035'%3E%3Cpath d='M0 30 Q15 0 30 30 T60 30 M0 15 Q15 45 30 15 T60 15 M0 45 Q15 15 30 45 T60 45'/%3E%3C/g%3E%3C/svg%3E")`,
        borderBottom: '1px solid var(--border-default)',
        position: 'relative',
        overflow: 'hidden',
        padding: '32px 24px 36px 24px',
      }}
    >
      {/* Decorative Faint Outline Seal Watermark */}
      <div
        style={{
          position: 'absolute',
          right: '-40px',
          top: '-30px',
          width: '280px',
          height: '280px',
          pointerEvents: 'none',
          opacity: 0.07,
          color: 'var(--accent-primary)',
        }}
      >
        <svg viewBox="0 0 200 200" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="100" cy="100" r="90" strokeDasharray="6 3" />
          <circle cx="100" cy="100" r="76" />
          <circle cx="100" cy="100" r="60" />
          <path d="M100 24 L100 176 M24 100 L176 100" strokeWidth="1.5" />
          <polygon points="100,45 115,85 158,85 123,110 136,152 100,126 64,152 77,110 42,85 85,85" strokeWidth="1.5" />
        </svg>
      </div>

      <div style={{ maxWidth: '1200px', margin: '0 auto', position: 'relative', zIndex: 1 }}>
        {/* Header section */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            marginBottom: '20px',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <span className="mono-step-num">01</span>
              <span className="section-label">Citizen Intake</span>
            </div>
            <h2
              style={{
                fontSize: '1.45rem',
                fontWeight: 600,
                color: 'var(--text-primary)',
                letterSpacing: '-0.015em',
                margin: 0,
                lineHeight: 1.3,
                fontFamily: 'var(--font-serif)',
              }}
            >
              Start an Official <span className="highlighter-amber">Public Service</span> Workflow
            </h2>
            <p
              style={{
                fontSize: '0.86rem',
                color: 'var(--text-secondary)',
                marginTop: '4px',
                marginBottom: 0,
                maxWidth: '720px',
              }}
            >
              Enter your administrative request in plain language. The system retrieves statutory rules, verifies vault facts, and provides full human oversight.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span className="badge badge-accent" style={{ fontSize: '0.75rem' }}>
              <ShieldCheck size={13} strokeWidth={1.75} /> Vault Consent Active
            </span>

            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="btn-secondary"
              style={{
                padding: '6px 12px',
                fontSize: '0.8rem',
                height: '32px',
                minHeight: '32px',
              }}
            >
              <Sliders size={13} strokeWidth={1.75} />
              {showAdvanced ? 'Hide Options' : 'Workflow Options'}
            </button>
          </div>
        </div>

        {/* Main Goal Form in clean white-cream surface */}
        <div
          className="card-pure"
          style={{
            padding: '20px 22px',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--border-default)',
          }}
        >
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: '14px' }}>
              <label
                htmlFor="citizen-request-input"
                style={{
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '4px 12px',
                  marginBottom: '6px',
                }}
              >
                <span>Request Details</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                  Plain citizen language (e.g. RTI request, Aadhaar update, or status tracking)
                </span>
              </label>

              <textarea
                id="citizen-request-input"
                rows={3}
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Type your official administrative request (e.g., 'Submit an RTI Online request to Ministry of External Affairs regarding passport dispatch timeline' or 'Track status of my Aadhaar update request')..."
                className="input-well"
                style={{
                  minHeight: '84px',
                  lineHeight: '1.5',
                  resize: 'vertical',
                }}
              />
            </div>

            {/* Suggestion Chips */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                marginBottom: '18px',
                flexWrap: 'wrap',
              }}
            >
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                Examples:
              </span>
              {POPULAR_PROMPTS.map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSelectPrompt(p)}
                  className="badge badge-neutral"
                  style={{
                    cursor: 'pointer',
                    border: '1px solid var(--border-default)',
                    padding: '4px 9px',
                    fontSize: '0.74rem',
                    color: 'var(--text-secondary)',
                    backgroundColor: 'var(--bg-stamped-slip)',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--accent-subtle)';
                    e.currentTarget.style.borderColor = 'var(--accent-border)';
                    e.currentTarget.style.color = 'var(--accent-primary)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--bg-stamped-slip)';
                    e.currentTarget.style.borderColor = 'var(--border-default)';
                    e.currentTarget.style.color = 'var(--text-secondary)';
                  }}
                >
                  {p.length > 50 ? `${p.slice(0, 48)}...` : p}
                </button>
              ))}
            </div>

            {/* Advanced Options Bar */}
            {showAdvanced && (
              <div
                style={{
                  padding: '14px 18px',
                  backgroundColor: 'var(--bg-sidebar-sand)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  marginBottom: '18px',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: '16px',
                }}
              >
                <div>
                  <label
                    style={{
                      fontSize: '0.76rem',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      display: 'block',
                      marginBottom: '6px',
                    }}
                  >
                    Language Adaptation
                  </label>
                  <select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    className="input-well"
                    style={{ padding: '6px 10px', fontSize: '0.82rem' }}
                  >
                    <option value="en">English (Official Format)</option>
                    <option value="hi">हिंदी (Hindi)</option>
                    <option value="ta">தமிழ் (Tamil)</option>
                  </select>
                </div>

                <div>
                  <label
                    style={{
                      fontSize: '0.76rem',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      display: 'block',
                      marginBottom: '6px',
                    }}
                  >
                    Safety & Dry-Run Mode
                  </label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        type="checkbox"
                        checked={isDryRun}
                        onChange={(e) => setIsDryRun(e.target.checked)}
                      />
                      <span>Dry run (Plan only, no portal interactions)</span>
                    </label>
                    <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        type="checkbox"
                        checked={stopBeforeSubmit}
                        onChange={(e) => setStopBeforeSubmit(e.target.checked)}
                      />
                      <span>Pause at confirmation page before final submission</span>
                    </label>
                  </div>
                </div>
              </div>
            )}

            {/* Bottom Actions */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingTop: '6px',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="stamped-slip">
                  <span className="stamped-slip-label">Protocol:</span> SIH-AGY-2026
                </span>
                <span className="stamped-slip">
                  <span className="stamped-slip-label">Audit:</span> Active
                </span>
              </div>

              <button
                type="submit"
                disabled={isLoading || !goal.trim()}
                className="btn-primary"
                style={{ padding: '9px 20px', fontSize: '0.88rem' }}
              >
                {isLoading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Analyzing Request...</span>
                  </>
                ) : (
                  <>
                    <span>Begin Application Workflow</span>
                    <ArrowRight size={15} strokeWidth={1.75} />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
