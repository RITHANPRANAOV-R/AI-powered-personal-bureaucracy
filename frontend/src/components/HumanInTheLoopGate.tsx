import React, { useState } from 'react';
import {
  FileLock2,
  KeyRound,
  Globe2,
  HelpCircle,
  XOctagon,
  CheckCircle2,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Check,
  FileEdit,
  Database,
  Save,
} from 'lucide-react';
import { OrchestratorState, ProfileFact, MissingPortalField } from '../types';

interface HumanInTheLoopGateProps {
  state: OrchestratorState;
  onSubmitConsent: (decisions: Record<string, 'save' | 'use_once' | 'skip'>, answers: Record<string, string>) => void;
  onSubmitAuthorization: (phrase: string) => void;
  onResumePause: () => void;
  onAbortWorkflow?: () => void;
  onSubmitClarifications: (answers: Record<string, string>) => void;
  onSubmitPortalFields?: (
    fieldValues: Record<string, string>,
    fieldLabels: Record<string, string>,
    saveToVault: Record<string, boolean>
  ) => void;
  isLoading: boolean;
}

export const HumanInTheLoopGate: React.FC<HumanInTheLoopGateProps> = ({
  state,
  onSubmitConsent,
  onSubmitAuthorization,
  onResumePause,
  onAbortWorkflow,
  onSubmitClarifications,
  onSubmitPortalFields,
  isLoading,
}) => {
  const status = state.workflow_status;

  // --- Missing Portal Form Fields State ---
  const missingPortalFields: MissingPortalField[] = state.user_input_payload?.missing_portal_fields || [];
  const [portalFieldValues, setPortalFieldValues] = useState<Record<string, string>>({});
  const [portalFieldSaveToVault, setPortalFieldSaveToVault] = useState<Record<string, boolean>>({});

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
  const recommendedPhrase = 'AUTHORIZE';

  // --- Clarifications State ---
  const questions = state.intent_result?.clarification_questions || [];
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});

  if (!status.startsWith('PAUSED_') && missingPortalFields.length === 0) {
    return null;
  }

  // Handle submit unknown portal fields
  const handlePortalFieldsSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading || !onSubmitPortalFields) return;
    const labelsMap: Record<string, string> = {};
    missingPortalFields.forEach((f) => {
      labelsMap[f.key] = f.label;
    });
    onSubmitPortalFields(portalFieldValues, labelsMap, portalFieldSaveToVault);
  };

  return (
    <div
      className="card"
      style={{
        margin: '0 20px 24px 20px',
        padding: '24px 28px',
        borderRadius: 'var(--radius-md)',
        borderLeft: '4px solid var(--state-warning-icon)',
        backgroundColor: 'var(--bg-surface)',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      {/* 0. UNKNOWN / UNFILLED PORTAL FORM FIELDS GATE */}
      {(status === 'PAUSED_UNKNOWN_FIELDS' || missingPortalFields.length > 0) && (
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              marginBottom: '18px',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: 'var(--radius-xs)',
                  backgroundColor: 'var(--state-warning-bg)',
                  border: '1px solid var(--state-warning-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--state-warning-icon)',
                }}
              >
                <FileEdit size={20} strokeWidth={1.75} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                  <span className="section-label">Portal Form Autofill Assistance</span>
                  <span className="badge badge-warning">Additional Details Required</span>
                </div>
                <h3
                  style={{
                    fontSize: '1.2rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    margin: 0,
                    fontFamily: 'var(--font-serif)',
                  }}
                >
                  Enter Missing Details for Official Portal
                </h3>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, marginTop: '2px' }}>
                  The government portal requires the following fields that were not in your vault. Enter them below: the assistant will fill them into the official website and update your encrypted knowledge base for future applications.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                className="btn-destructive-outline"
              >
                <XOctagon size={14} strokeWidth={1.75} />
                <span>Abort Workflow</span>
              </button>
            )}
          </div>

          <form onSubmit={handlePortalFieldsSubmit}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                gap: '16px',
                marginBottom: '20px',
                backgroundColor: 'var(--bg-sidebar-sand)',
                padding: '18px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-default)',
              }}
            >
              {missingPortalFields.map((field) => (
                <div
                  key={field.key}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    backgroundColor: 'var(--bg-surface)',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-xs)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <label
                      style={{
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        color: 'var(--text-primary)',
                      }}
                    >
                      {field.label} {field.is_required && <span style={{ color: 'var(--state-danger-text)' }}>*</span>}
                    </label>
                    <span className="stamped-slip" style={{ fontSize: '0.68rem', padding: '1px 5px' }}>
                      {field.key}
                    </span>
                  </div>

                  {field.type === 'select' && field.options && field.options.length > 0 ? (
                    <select
                      value={portalFieldValues[field.key] || ''}
                      onChange={(e) =>
                        setPortalFieldValues({ ...portalFieldValues, [field.key]: e.target.value })
                      }
                      className="input-well"
                      style={{ fontSize: '0.84rem', padding: '8px 10px' }}
                    >
                      <option value="">-- Select from official options --</option>
                      {field.options.map((opt, i) => (
                        <option key={i} value={opt.label || opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  ) : field.type === 'textarea' ? (
                    <textarea
                      rows={3}
                      value={portalFieldValues[field.key] || ''}
                      placeholder={field.placeholder || `Enter ${field.label}...`}
                      onChange={(e) =>
                        setPortalFieldValues({ ...portalFieldValues, [field.key]: e.target.value })
                      }
                      className="input-well"
                      style={{ fontSize: '0.84rem', padding: '8px 10px', resize: 'vertical' }}
                    />
                  ) : (
                    <input
                      type="text"
                      value={portalFieldValues[field.key] || ''}
                      placeholder={field.placeholder || `Enter ${field.label}...`}
                      onChange={(e) =>
                        setPortalFieldValues({ ...portalFieldValues, [field.key]: e.target.value })
                      }
                      className="input-well"
                      style={{ fontSize: '0.84rem', padding: '8px 10px' }}
                    />
                  )}

                  <label
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      fontSize: '0.74rem',
                      color: 'var(--text-secondary)',
                      marginTop: '4px',
                      cursor: 'pointer',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={portalFieldSaveToVault[field.key] !== false}
                      onChange={(e) =>
                        setPortalFieldSaveToVault({
                          ...portalFieldSaveToVault,
                          [field.key]: e.target.checked,
                        })
                      }
                    />
                    <span>Save to Knowledge Base / Vault for future applications</span>
                  </label>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="stamped-slip">
                  <Database size={13} strokeWidth={1.75} /> Auto-Syncs to Profile Vault
                </span>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="btn-primary"
                style={{ padding: '9px 22px' }}
              >
                <Save size={15} strokeWidth={1.75} />
                <span>Fill in Official Portal & Save to Knowledge Base</span>
                <ArrowRight size={14} strokeWidth={1.75} />
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 1. FACT CONSENT GATE */}
      {status === 'PAUSED_FACT_CONSENT' && missingPortalFields.length === 0 && (
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              marginBottom: '18px',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: 'var(--radius-xs)',
                  backgroundColor: 'var(--state-warning-bg)',
                  border: '1px solid var(--state-warning-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--state-warning-icon)',
                }}
              >
                <FileLock2 size={20} strokeWidth={1.75} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                  <span className="section-label">Human Consent Checkpoint</span>
                  <span className="badge badge-warning">Action Required</span>
                </div>
                <h3
                  style={{
                    fontSize: '1.2rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    margin: 0,
                    fontFamily: 'var(--font-serif)',
                  }}
                >
                  Verify Personal Profile Facts
                </h3>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, marginTop: '2px' }}>
                  Review personal facts retrieved from your encrypted vault before submitting them to government portals.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                className="btn-destructive-outline"
              >
                <XOctagon size={14} strokeWidth={1.75} />
                <span>Abort Workflow</span>
              </button>
            )}
          </div>

          {unconfirmedFacts.length === 0 ? (
            <div
              style={{
                padding: '14px 18px',
                background: 'var(--bg-stamped-slip)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-secondary)',
                fontSize: '0.85rem',
                marginBottom: '16px',
              }}
            >
              All profile facts are verified. Click below to continue execution.
            </div>
          ) : (
            <div style={{ overflowX: 'auto', marginBottom: '20px' }}>
              <table className="table-editorial">
                <thead>
                  <tr>
                    <th>Fact Identifier</th>
                    <th>Extracted / Verified Value</th>
                    <th>Source Document</th>
                    <th>Consent Action</th>
                  </tr>
                </thead>
                <tbody>
                  {unconfirmedFacts.map((fact) => (
                    <tr key={fact.key}>
                      <td style={{ fontWeight: 600 }}>
                        <span className="stamped-slip">{fact.key}</span>
                      </td>
                      <td>
                        <input
                          type="text"
                          value={editedValues[fact.key] ?? fact.value}
                          onChange={(e) =>
                            setEditedValues({ ...editedValues, [fact.key]: e.target.value })
                          }
                          className="input-well"
                          style={{ maxWidth: '280px', padding: '6px 10px', fontSize: '0.85rem' }}
                        />
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                        {fact.source_ref}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            type="button"
                            onClick={() => setDecisions({ ...decisions, [fact.key]: 'save' })}
                            style={{
                              padding: '4px 10px',
                              borderRadius: 'var(--radius-xs)',
                              fontSize: '0.76rem',
                              fontWeight: 500,
                              cursor: 'pointer',
                              border:
                                decisions[fact.key] === 'save'
                                  ? '1px solid var(--state-verified-border)'
                                  : '1px solid var(--border-default)',
                              backgroundColor:
                                decisions[fact.key] === 'save'
                                  ? 'var(--state-verified-bg)'
                                  : 'var(--bg-surface)',
                              color:
                                decisions[fact.key] === 'save'
                                  ? 'var(--state-verified-text)'
                                  : 'var(--text-secondary)',
                            }}
                          >
                            Save to Vault
                          </button>
                          <button
                            type="button"
                            onClick={() => setDecisions({ ...decisions, [fact.key]: 'use_once' })}
                            style={{
                              padding: '4px 10px',
                              borderRadius: 'var(--radius-xs)',
                              fontSize: '0.76rem',
                              fontWeight: 500,
                              cursor: 'pointer',
                              border:
                                decisions[fact.key] === 'use_once'
                                  ? '1px solid var(--accent-border)'
                                  : '1px solid var(--border-default)',
                              backgroundColor:
                                decisions[fact.key] === 'use_once'
                                  ? 'var(--accent-subtle)'
                                  : 'var(--bg-surface)',
                              color:
                                decisions[fact.key] === 'use_once'
                                  ? 'var(--accent-primary)'
                                  : 'var(--text-secondary)',
                            }}
                          >
                            Use Once
                          </button>
                          <button
                            type="button"
                            onClick={() => setDecisions({ ...decisions, [fact.key]: 'skip' })}
                            style={{
                              padding: '4px 10px',
                              borderRadius: 'var(--radius-xs)',
                              fontSize: '0.76rem',
                              fontWeight: 500,
                              cursor: 'pointer',
                              border:
                                decisions[fact.key] === 'skip'
                                  ? '1px solid var(--state-danger-border)'
                                  : '1px solid var(--border-default)',
                              backgroundColor:
                                decisions[fact.key] === 'skip'
                                  ? 'var(--state-danger-bg)'
                                  : 'var(--bg-surface)',
                              color:
                                decisions[fact.key] === 'skip'
                                  ? 'var(--state-danger-text)'
                                  : 'var(--text-secondary)',
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
            >
              Set All to 'Save'
            </button>
            <button
              onClick={() => onSubmitConsent(decisions, editedValues)}
              disabled={isLoading}
              className="btn-primary"
            >
              <CheckCircle2 size={16} strokeWidth={1.75} />
              <span>Confirm Vault Consent & Continue</span>
            </button>
          </div>
        </div>
      )}

      {/* 2. EXPLICIT AUTHORIZATION GATE */}
      {status === 'PAUSED_NEEDS_AUTHORIZATION' && missingPortalFields.length === 0 && (
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              marginBottom: '18px',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: 'var(--radius-xs)',
                  backgroundColor: 'var(--accent-subtle)',
                  border: '1px solid var(--accent-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--accent-primary)',
                }}
              >
                <KeyRound size={20} strokeWidth={1.75} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                  <span className="section-label">Zero-Trust Authorization</span>
                  <span className="badge badge-warning">Safety Checkpoint</span>
                </div>
                <h3
                  style={{
                    fontSize: '1.2rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    margin: 0,
                    fontFamily: 'var(--font-serif)',
                  }}
                >
                  Confirm Execution Permission
                </h3>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, marginTop: '2px' }}>
                  Statutory planning is complete. Enter the confirmation keyword to authorize autonomous portal interaction.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                className="btn-destructive-outline"
              >
                <XOctagon size={14} strokeWidth={1.75} />
                <span>Abort Workflow</span>
              </button>
            )}
          </div>

          <div
            style={{
              backgroundColor: 'var(--bg-stamped-slip)',
              border: '1px dashed var(--border-dashed-slip)',
              borderRadius: 'var(--radius-sm)',
              padding: '14px 18px',
              marginBottom: '16px',
            }}
          >
            <div
              style={{
                fontSize: '0.74rem',
                fontWeight: 600,
                color: 'var(--text-secondary)',
                textTransform: 'uppercase',
                marginBottom: '6px',
              }}
            >
              Required Authorization Keyword
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
              <span className="stamped-slip" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--accent-primary)' }}>
                {recommendedPhrase}
              </span>
              <button
                type="button"
                onClick={() => setAuthPhrase(recommendedPhrase)}
                className="btn-secondary"
                style={{ padding: '5px 12px', fontSize: '0.78rem' }}
              >
                <Sparkles size={13} strokeWidth={1.75} /> Auto-fill Keyword
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
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <input
                type="text"
                value={authPhrase}
                onChange={(e) => setAuthPhrase(e.target.value)}
                placeholder={`Type or auto-fill '${recommendedPhrase}' to proceed...`}
                className="input-well"
                style={{
                  flex: 1,
                  minWidth: '240px',
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '0.04em',
                }}
              />

              <button
                type="submit"
                disabled={isLoading || !authPhrase.trim()}
                className="btn-primary"
                style={{ padding: '9px 22px' }}
              >
                <KeyRound size={15} strokeWidth={1.75} />
                <span>Authorize & Execute</span>
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 3. CAPTCHA / PAYMENT CHALLENGE GATE */}
      {(status === 'PAUSED_CAPTCHA' || status === 'PAUSED_PAYMENT') && missingPortalFields.length === 0 && (
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              marginBottom: '18px',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: 'var(--radius-xs)',
                  backgroundColor: 'var(--state-warning-bg)',
                  border: '1px solid var(--state-warning-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--state-warning-icon)',
                }}
              >
                <Globe2 size={20} strokeWidth={1.75} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                  <span className="section-label">Assisted Portal Automation</span>
                  <span className="badge badge-warning">
                    {status === 'PAUSED_CAPTCHA' ? 'CAPTCHA / OTP Challenge' : 'Fee Payment Required'}
                  </span>
                </div>
                <h3
                  style={{
                    fontSize: '1.2rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    margin: 0,
                    fontFamily: 'var(--font-serif)',
                  }}
                >
                  {status === 'PAUSED_CAPTCHA'
                    ? 'Complete Portal Verification in Browser'
                    : 'Complete Official Portal Payment'}
                </h3>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, marginTop: '2px' }}>
                  The browser session is loaded with all vault facts autofilled. Please solve the CAPTCHA or complete OTP verification in the portal window, then click <strong>Resume Assistant</strong>.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                className="btn-destructive-outline"
              >
                <XOctagon size={14} strokeWidth={1.75} />
                <span>Abort Workflow</span>
              </button>
            )}
          </div>

          <div
            style={{
              padding: '14px 18px',
              backgroundColor: 'var(--bg-sidebar-sand)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="status-dot status-dot-green" />
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Chromium Session Ready — Awaiting Citizen Interaction
              </span>
            </div>

            <button
              onClick={onResumePause}
              disabled={isLoading}
              className="btn-primary"
              style={{
                backgroundColor: 'var(--state-verified-text)',
                borderColor: '#0f3a1d',
                color: '#ffffff',
                padding: '9px 22px',
              }}
            >
              <CheckCircle2 size={16} strokeWidth={1.75} />
              <span>{isLoading ? 'Resuming Assistant...' : 'Resume Assistant'}</span>
            </button>
          </div>
        </div>
      )}

      {/* 4. CLARIFICATION QUESTIONS GATE */}
      {status === 'PAUSED_NEEDS_INPUT' && missingPortalFields.length === 0 && (
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              marginBottom: '18px',
              flexWrap: 'wrap',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: 'var(--radius-xs)',
                  backgroundColor: 'var(--accent-subtle)',
                  border: '1px solid var(--accent-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--accent-primary)',
                }}
              >
                <HelpCircle size={20} strokeWidth={1.75} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                  <span className="section-label">Intent Clarification</span>
                  <span className="badge badge-warning">Input Needed</span>
                </div>
                <h3
                  style={{
                    fontSize: '1.2rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    margin: 0,
                    fontFamily: 'var(--font-serif)',
                  }}
                >
                  Additional Details Required
                </h3>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, marginTop: '2px' }}>
                  Please answer the following questions to formulate the exact statutory execution route.
                </p>
              </div>
            </div>

            {onAbortWorkflow && (
              <button
                type="button"
                onClick={onAbortWorkflow}
                disabled={isLoading}
                className="btn-destructive-outline"
              >
                <XOctagon size={14} strokeWidth={1.75} />
                <span>Abort Workflow</span>
              </button>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '18px' }}>
            {questions.map((q) => (
              <div key={q}>
                <label
                  style={{
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    display: 'block',
                    marginBottom: '6px',
                  }}
                >
                  {q}
                </label>
                <input
                  type="text"
                  value={clarificationAnswers[q] || ''}
                  onChange={(e) =>
                    setClarificationAnswers({ ...clarificationAnswers, [q]: e.target.value })
                  }
                  placeholder="Type your answer here..."
                  className="input-well"
                />
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={() => onSubmitClarifications(clarificationAnswers)}
              disabled={isLoading}
              className="btn-primary"
            >
              <ArrowRight size={15} strokeWidth={1.75} />
              <span>Submit Clarifications & Resume</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
