import React, { useState } from 'react';
import {
  ShieldAlert,
  KeyRound,
  CheckCircle,
  FileLock2,
  AlertTriangle,
  ArrowRight,
  Sparkles,
  Bot,
  Terminal,
  HelpCircle,
  XOctagon,
  Eye,
  RefreshCw,
} from 'lucide-react';
import { OrchestratorState, ProfileFact } from '../types';

interface HumanInTheLoopGateProps {
  state: OrchestratorState;
  onSubmitConsent: (decisions: Record<string, 'save' | 'use_once' | 'skip'>, answers: Record<string, string>) => void;
  onSubmitAuthorization: (phrase: string) => void;
  onResumePause: () => void;
  onAbortWorkflow?: () => void;
  onSubmitClarifications: (answers: Record<string, string>) => void;
  isLoading: boolean;
}

export const HumanInTheLoopGate: React.FC<HumanInTheLoopGateProps> = ({
  state,
  onSubmitConsent,
  onSubmitAuthorization,
  onResumePause,
  onAbortWorkflow,
  onSubmitClarifications,
  isLoading,
}) => {
  const status = state.workflow_status;

  // --- Fact Consent State ---
  const unconfirmedFacts: ProfileFact[] = (state.profile_result?.relevant_facts || []).filter(
    (f) => !f.confirmed_by_user
  );
  const [decisions, setDecisions] = useState<Record<string, 'save' | 'use_once' | 'skip'>>(() => {
    const init: Record<string, 'save' | 'use_once' | 'skip'> = {};
    unconfirmedFacts.forEach((f) => {
      init[f.key] = 'save';
    });
    return init;
  });
  const [editedValues, setEditedValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    unconfirmedFacts.forEach((f) => {
      init[f.key] = f.value;
    });
    return init;
  });

  // --- Authorization State ---
  const [authPhrase, setAuthPhrase] = useState('');
  
  // Standard required authorization phrase is always AUTHORIZE
  const recommendedPhrase = 'AUTHORIZE';

  // --- Clarifications State ---
  const questions = state.intent_result?.clarification_questions || [];
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});

  if (!status.startsWith('PAUSED_')) {
    return null;
  }

  return (
    <div
      className="glass-panel-elevated animate-fade-in"
      style={{
        margin: '0 20px 24px 20px',
        padding: '24px',
        border: '1px solid rgba(245, 158, 11, 0.45)',
        boxShadow: '0 0 35px rgba(245, 158, 11, 0.18)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Top Warning Glow Line */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '3px',
          background: 'linear-gradient(90deg, #f59e0b, #ef4444, #f59e0b)',
        }}
      />

      {/* 1. FACT CONSENT GATE */}
      {status === 'PAUSED_FACT_CONSENT' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  background: 'rgba(245, 158, 11, 0.2)',
                  border: '1px solid rgba(245, 158, 11, 0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <FileLock2 size={24} color="#fbbf24" />
              </div>
              <div>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#fbbf24' }}>
                  Human-in-the-Loop: Citizen Fact Consent Required
                </h3>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Review personal vault facts before compliance validation gates proceed.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                style={{
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#f87171',
                  borderRadius: '10px',
                  padding: '8px 16px',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <XOctagon size={15} />
                Abort Workflow
              </button>
            )}
          </div>

          {unconfirmedFacts.length === 0 ? (
            <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '10px', color: 'var(--text-muted)' }}>
              All facts are confirmed. Click below to continue.
            </div>
          ) : (
            <div style={{ overflowX: 'auto', marginBottom: '20px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-medium)', textAlign: 'left', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '10px' }}>Fact Key</th>
                    <th style={{ padding: '10px' }}>Extracted Value</th>
                    <th style={{ padding: '10px' }}>Source Ref</th>
                    <th style={{ padding: '10px' }}>Consent Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {unconfirmedFacts.map((fact) => (
                    <tr key={fact.key} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '12px 10px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        <code>{fact.key}</code>
                      </td>
                      <td style={{ padding: '12px 10px' }}>
                        <input
                          type="text"
                          value={editedValues[fact.key] ?? fact.value}
                          onChange={(e) => setEditedValues({ ...editedValues, [fact.key]: e.target.value })}
                          style={{
                            background: 'rgba(5, 7, 12, 0.8)',
                            border: '1px solid var(--border-medium)',
                            borderRadius: '6px',
                            padding: '6px 10px',
                            color: '#ffffff',
                            fontSize: '0.85rem',
                            width: '100%',
                            maxWidth: '260px',
                          }}
                        />
                      </td>
                      <td style={{ padding: '12px 10px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                        {fact.source_ref}
                      </td>
                      <td style={{ padding: '12px 10px' }}>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            type="button"
                            onClick={() => setDecisions({ ...decisions, [fact.key]: 'save' })}
                            style={{
                              padding: '4px 10px',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              border: decisions[fact.key] === 'save' ? '1px solid #10b981' : '1px solid var(--border-subtle)',
                              background: decisions[fact.key] === 'save' ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
                              color: decisions[fact.key] === 'save' ? '#6ee7b7' : 'var(--text-muted)',
                            }}
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            onClick={() => setDecisions({ ...decisions, [fact.key]: 'use_once' })}
                            style={{
                              padding: '4px 10px',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              border: decisions[fact.key] === 'use_once' ? '1px solid #38bdf8' : '1px solid var(--border-subtle)',
                              background: decisions[fact.key] === 'use_once' ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                              color: decisions[fact.key] === 'use_once' ? '#7dd3fc' : 'var(--text-muted)',
                            }}
                          >
                            Use Once
                          </button>
                          <button
                            type="button"
                            onClick={() => setDecisions({ ...decisions, [fact.key]: 'skip' })}
                            style={{
                              padding: '4px 10px',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              border: decisions[fact.key] === 'skip' ? '1px solid #f43f5e' : '1px solid var(--border-subtle)',
                              background: decisions[fact.key] === 'skip' ? 'rgba(244, 63, 94, 0.2)' : 'transparent',
                              color: decisions[fact.key] === 'skip' ? '#fda4af' : 'var(--text-muted)',
                            }}
                          >
                            Skip
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <button
              onClick={() => {
                const allSave: Record<string, 'save'> = {};
                unconfirmedFacts.forEach((f) => (allSave[f.key] = 'save'));
                setDecisions(allSave);
              }}
              className="btn-secondary"
              style={{ fontSize: '0.85rem' }}
            >
              Set All to 'Save'
            </button>
            <button
              onClick={() => onSubmitConsent(decisions, editedValues)}
              disabled={isLoading}
              className="btn-accent-emerald"
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <CheckCircle size={16} />
              Confirm Fact Consent & Continue
            </button>
          </div>
        </div>
      )}

      {/* 2. EXPLICIT AUTHORIZATION GATE */}
      {status === 'PAUSED_NEEDS_AUTHORIZATION' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  background: 'rgba(99, 102, 241, 0.25)',
                  border: '1px solid rgba(99, 102, 241, 0.5)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <KeyRound size={24} color="#818cf8" />
              </div>
              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#ffffff' }}>
                  Safety Checkpoint: Explicit Authorization Required
                </h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  Workflow planning and compliance gates passed. Enter authorization phrase to grant permission to execute.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                style={{
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#f87171',
                  borderRadius: '10px',
                  padding: '8px 16px',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <XOctagon size={15} />
                Abort Workflow
              </button>
            )}
          </div>

          <div
            style={{
              background: 'rgba(5, 7, 14, 0.8)',
              border: '1px solid var(--border-medium)',
              borderRadius: '14px',
              padding: '18px',
              marginBottom: '18px',
            }}
          >
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.04em' }}>
              Required Authorization Phrase:
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
              <code style={{ fontSize: '0.98rem', fontWeight: 700, color: '#67e8f9', background: 'rgba(6, 182, 212, 0.12)', padding: '8px 14px', borderRadius: '8px', border: '1px solid rgba(6, 182, 212, 0.3)', letterSpacing: '0.02em' }}>
                {recommendedPhrase}
              </code>
              <button
                type="button"
                onClick={() => setAuthPhrase(recommendedPhrase)}
                className="btn-secondary"
                style={{ padding: '8px 14px', fontSize: '0.82rem', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Sparkles size={14} color="#38bdf8" /> Auto-fill Phrase
              </button>
            </div>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (authPhrase.trim() && !isLoading) {
                onSubmitAuthorization(authPhrase);
              }
            }}
          >
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <input
                type="text"
                value={authPhrase}
                onChange={(e) => setAuthPhrase(e.target.value)}
                placeholder={`Type or auto-fill: ${recommendedPhrase}`}
                style={{
                  flex: 1,
                  minWidth: '280px',
                  background: 'rgba(5, 7, 14, 0.9)',
                  border: '1px solid var(--border-bright)',
                  borderRadius: '12px',
                  padding: '12px 16px',
                  color: '#ffffff',
                  fontSize: '0.94rem',
                  fontFamily: 'var(--font-mono)',
                  outline: 'none',
                }}
              />

              <button
                type="submit"
                disabled={isLoading || !authPhrase.trim()}
                className="btn-accent-amber"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '12px 28px',
                  borderRadius: '12px',
                  fontSize: '0.94rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                <KeyRound size={17} />
                Authorize & Execute
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 3. CAPTCHA / PAYMENT CHALLENGE GATE */}
      {(status === 'PAUSED_CAPTCHA' || status === 'PAUSED_PAYMENT') && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  background: 'rgba(244, 63, 94, 0.2)',
                  border: '1px solid rgba(244, 63, 94, 0.45)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  animation: 'pulse 2s infinite',
                }}
              >
                <Terminal size={24} color="#f43f5e" />
              </div>
              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f43f5e' }}>
                  {status === 'PAUSED_CAPTCHA' ? 'Live Browser: CAPTCHA / Verification Checkpoint' : 'Live Browser: Portal Payment Required'}
                </h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  The Chromium browser is open. Form fields have been filled automatically from your vault. Please complete the CAPTCHA or OTP on the portal page, then click <strong>Resume Assistant</strong>.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                style={{
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#f87171',
                  borderRadius: '10px',
                  padding: '8px 16px',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <XOctagon size={15} />
                Abort Workflow
              </button>
            )}
          </div>

          <div
            style={{
              padding: '16px 20px',
              background: 'rgba(5, 7, 14, 0.7)',
              border: '1px solid var(--border-medium)',
              borderRadius: '12px',
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10b981', boxShadow: '0 0 10px #10b981' }} />
              <span style={{ fontSize: '0.9rem', color: '#ffffff', fontWeight: 600 }}>
                Browser Session Active (Chromium) — Ready for Human Action
              </span>
            </div>

            <button
              onClick={onResumePause}
              disabled={isLoading}
              className="btn-accent-emerald"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '12px 28px',
                borderRadius: '12px',
                fontSize: '0.95rem',
                fontWeight: 700,
                boxShadow: '0 0 20px rgba(16, 185, 129, 0.35)',
              }}
            >
              <CheckCircle size={18} />
              {isLoading ? 'Submitting & Resuming...' : 'Resume Assistant'}
            </button>
          </div>
        </div>
      )}

      {/* 4. CLARIFICATION QUESTIONS GATE */}
      {status === 'PAUSED_NEEDS_INPUT' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  background: 'rgba(6, 182, 212, 0.2)',
                  border: '1px solid rgba(6, 182, 212, 0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <HelpCircle size={24} color="#06b6d4" />
              </div>
              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#06b6d4' }}>
                  Intent Clarification Needed
                </h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  The Intent Understanding Agent requires additional details to formulate the precise workflow plan.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                style={{
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#f87171',
                  borderRadius: '10px',
                  padding: '8px 16px',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <XOctagon size={15} />
                Abort Workflow
              </button>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '20px' }}>
            {questions.map((q) => (
              <div key={q}>
                <label style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '8px' }}>
                  {q}
                </label>
                <input
                  type="text"
                  value={clarificationAnswers[q] || ''}
                  onChange={(e) => setClarificationAnswers({ ...clarificationAnswers, [q]: e.target.value })}
                  placeholder="Type your clarification answer..."
                  style={{
                    width: '100%',
                    background: 'rgba(5, 7, 14, 0.85)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                    color: '#ffffff',
                    fontSize: '0.9rem',
                    outline: 'none',
                  }}
                />
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={() => onSubmitClarifications(clarificationAnswers)}
              disabled={isLoading}
              className="btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 28px', borderRadius: '12px' }}
            >
              <ArrowRight size={16} />
              Submit Answers & Resume
            </button>
          </div>
        </div>
      )}

    </div>
  );
};
