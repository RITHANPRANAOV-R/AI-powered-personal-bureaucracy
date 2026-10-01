import React, { useState } from 'react';
import {
  FileText,
  CheckCircle2,
  Clock,
  ExternalLink,
  ShieldCheck,
  Download,
  Copy,
  Check,
  Layers,
  Search,
  Code2,
  FileCheck2,
  UserCheck,
} from 'lucide-react';
import { OrchestratorState } from '../types';

interface WorkflowResultsViewProps {
  state: OrchestratorState;
}

export const WorkflowResultsView: React.FC<WorkflowResultsViewProps> = ({ state }) => {
  const [activeSubTab, setActiveSubTab] = useState<
    'response' | 'plan' | 'evidence' | 'profile' | 'compliance' | 'contracts'
  >('response');
  const [copied, setCopied] = useState(false);

  const citizen = state.citizen_response;
  const plan = state.workflow_plan || state.workflow_plan_original;
  const evidence = state.evidence_result;
  const profile = state.profile_result;
  const validation = state.validation_result;

  const handleCopyMarkdown = () => {
    if (citizen?.formatted_markdown) {
      navigator.clipboard.writeText(citizen.formatted_markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownloadReport = () => {
    if (!citizen) return;
    const blob = new Blob([citizen.formatted_markdown || citizen.summary], {
      type: 'text/markdown',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bureaucracy_report_${state.workflow_id.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="card card-watermark"
      style={{
        margin: '0 20px 24px 20px',
        padding: '24px 28px',
        borderRadius: 'var(--radius-md)',
        backgroundColor: 'var(--bg-surface)',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      {/* Top Header Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '14px',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '18px',
          marginBottom: '20px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span className="mono-step-num">09</span>
            <span className="section-label">Official Inspection</span>
            <span
              className={
                state.workflow_status === 'COMPLETED' ? 'badge badge-verified' : 'badge badge-accent'
              }
            >
              {state.workflow_status === 'COMPLETED' ? (
                <>
                  <CheckCircle2 size={13} strokeWidth={2} /> Verified Completion
                </>
              ) : (
                state.workflow_status
              )}
            </span>
          </div>

          <h3
            style={{
              fontSize: '1.25rem',
              fontWeight: 600,
              color: 'var(--text-primary)',
              margin: 0,
              fontFamily: 'var(--font-serif)',
            }}
          >
            {citizen?.headline || 'Citizen Guidance & Application Records'}
          </h3>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px', flexWrap: 'wrap' }}>
            <span className="stamped-slip">
              <span className="stamped-slip-label">Workflow ID:</span> {state.workflow_id.slice(0, 8)}...
            </span>
            <span className="stamped-slip">
              <span className="stamped-slip-label">Jurisdiction:</span> IN-UNION
            </span>
          </div>
        </div>

        {/* Tab Switcher */}
        <div
          style={{
            display: 'flex',
            gap: '4px',
            backgroundColor: 'var(--bg-sidebar-sand)',
            padding: '3px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-default)',
            flexWrap: 'wrap',
          }}
        >
          <button
            onClick={() => setActiveSubTab('response')}
            className={`tab-editorial-btn ${activeSubTab === 'response' ? 'active' : ''}`}
            style={{ borderRadius: 'var(--radius-xs)' }}
          >
            <FileText size={14} strokeWidth={1.75} />
            Citizen Guidance
          </button>
          <button
            onClick={() => setActiveSubTab('plan')}
            className={`tab-editorial-btn ${activeSubTab === 'plan' ? 'active' : ''}`}
            style={{ borderRadius: 'var(--radius-xs)' }}
          >
            <Layers size={14} strokeWidth={1.75} />
            Execution Plan ({plan?.steps.length || 0})
          </button>
          <button
            onClick={() => setActiveSubTab('evidence')}
            className={`tab-editorial-btn ${activeSubTab === 'evidence' ? 'active' : ''}`}
            style={{ borderRadius: 'var(--radius-xs)' }}
          >
            <Search size={14} strokeWidth={1.75} />
            Verified Evidence
          </button>
          <button
            onClick={() => setActiveSubTab('profile')}
            className={`tab-editorial-btn ${activeSubTab === 'profile' ? 'active' : ''}`}
            style={{ borderRadius: 'var(--radius-xs)' }}
          >
            <UserCheck size={14} strokeWidth={1.75} />
            Citizen Profile
          </button>
          <button
            onClick={() => setActiveSubTab('compliance')}
            className={`tab-editorial-btn ${activeSubTab === 'compliance' ? 'active' : ''}`}
            style={{ borderRadius: 'var(--radius-xs)' }}
          >
            <ShieldCheck size={14} strokeWidth={1.75} />
            Compliance Audit
          </button>
          <button
            onClick={() => setActiveSubTab('contracts')}
            className={`tab-editorial-btn ${activeSubTab === 'contracts' ? 'active' : ''}`}
            style={{ borderRadius: 'var(--radius-xs)' }}
          >
            <Code2 size={14} strokeWidth={1.75} />
            State JSON
          </button>
        </div>
      </div>

      {/* SUBTAB 1: CITIZEN GUIDANCE */}
      {activeSubTab === 'response' && (
        <div>
          {citizen ? (
            <div>
              {/* Summary Card */}
              <div
                style={{
                  backgroundColor: 'var(--accent-subtle)',
                  border: '1px solid var(--accent-border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '18px 20px',
                  marginBottom: '20px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '10px',
                    flexWrap: 'wrap',
                    gap: '10px',
                  }}
                >
                  <span className="badge badge-accent" style={{ fontSize: '0.74rem' }}>
                    Official Guidance Summary
                  </span>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={handleCopyMarkdown}
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.76rem' }}
                    >
                      {copied ? (
                        <Check size={13} strokeWidth={2} style={{ color: 'var(--state-verified-icon)' }} />
                      ) : (
                        <Copy size={13} strokeWidth={1.75} />
                      )}
                      <span>{copied ? 'Copied' : 'Copy MD'}</span>
                    </button>
                    <button
                      onClick={handleDownloadReport}
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.76rem' }}
                    >
                      <Download size={13} strokeWidth={1.75} />
                      <span>Export Report</span>
                    </button>
                  </div>
                </div>
                <p
                  style={{
                    fontSize: '0.94rem',
                    color: 'var(--text-primary)',
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  {citizen.summary}
                </p>
              </div>

              {/* Immediate Next Step */}
              {citizen.citizen_next_step && (
                <div
                  style={{
                    backgroundColor: 'var(--state-verified-bg)',
                    border: '1px solid var(--state-verified-border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '16px 20px',
                    marginBottom: '20px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <CheckCircle2 size={16} strokeWidth={2} style={{ color: 'var(--state-verified-icon)' }} />
                    <h4
                      style={{
                        fontSize: '0.92rem',
                        fontWeight: 600,
                        color: 'var(--state-verified-text)',
                        margin: 0,
                      }}
                    >
                      Immediate Citizen Action: {citizen.citizen_next_step.title}
                    </h4>
                  </div>
                  <p
                    style={{
                      fontSize: '0.85rem',
                      color: 'var(--text-secondary)',
                      margin: 0,
                      lineHeight: 1.5,
                    }}
                  >
                    {citizen.citizen_next_step.description}
                  </p>
                </div>
              )}

              {/* Pending Actions */}
              {citizen.pending_actions && citizen.pending_actions.length > 0 && (
                <div style={{ marginBottom: '20px' }}>
                  <h4
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: 'var(--text-secondary)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      marginBottom: '10px',
                    }}
                  >
                    Pending Checkpoints & Follow-ups
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {citizen.pending_actions.map((pa) => (
                      <div
                        key={pa.step_id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '10px 14px',
                          backgroundColor: 'var(--bg-sidebar-sand)',
                          border: '1px solid var(--border-default)',
                          borderRadius: 'var(--radius-sm)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span className="badge badge-warning" style={{ fontSize: '0.7rem' }}>
                            {pa.step_id}
                          </span>
                          <span style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                            {pa.action_title}
                          </span>
                        </div>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          {pa.reason}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Formatted Markdown Output */}
              {citizen.formatted_markdown && (
                <div>
                  <h4
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: 'var(--text-secondary)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      marginBottom: '8px',
                    }}
                  >
                    Full Official Record Document
                  </h4>
                  <div
                    style={{
                      backgroundColor: 'var(--bg-stamped-slip)',
                      border: '1px dashed var(--border-dashed-slip)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '16px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.84rem',
                      whiteSpace: 'pre-wrap',
                      lineHeight: 1.6,
                      maxHeight: '380px',
                      overflowY: 'auto',
                      color: 'var(--text-primary)',
                    }}
                  >
                    {citizen.formatted_markdown}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
              Guidance report will be generated as soon as the workflow completes.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 2: EXECUTION PLAN */}
      {activeSubTab === 'plan' && (
        <div>
          {plan ? (
            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '14px',
                  flexWrap: 'wrap',
                  gap: '8px',
                }}
              >
                <span className="badge badge-accent">
                  Service: {plan.service_name} • Type: {plan.task_type}
                </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Estimated Total Duration: ~{plan.estimated_total_minutes} mins
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {plan.steps.map((st, i) => (
                  <div
                    key={st.step_id}
                    style={{
                      padding: '12px 16px',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'var(--bg-sidebar-sand)',
                      border: '1px solid var(--border-default)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '14px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div
                        style={{
                          width: '24px',
                          height: '24px',
                          borderRadius: 'var(--radius-xs)',
                          backgroundColor: 'var(--accent-primary)',
                          color: '#ffffff',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.74rem',
                          fontWeight: 600,
                        }}
                      >
                        {i + 1}
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                            {st.title}
                          </span>
                          <span className="badge badge-neutral" style={{ fontSize: '0.68rem' }}>
                            {st.actor}
                          </span>
                          {st.requires_user_approval && (
                            <span className="badge badge-warning" style={{ fontSize: '0.68rem' }}>
                              Approval Required
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px', margin: 0 }}>
                          {st.description}
                        </p>
                      </div>
                    </div>

                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <span
                        style={{
                          fontSize: '0.75rem',
                          color: 'var(--text-muted)',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <Clock size={12} strokeWidth={1.75} /> {st.estimated_minutes}m
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
              No workflow plan generated yet.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 3: VERIFIED EVIDENCE */}
      {activeSubTab === 'evidence' && (
        <div>
          {evidence ? (
            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '16px',
                  flexWrap: 'wrap',
                  gap: '8px',
                }}
              >
                <span className="badge badge-verified">
                  Average Trust Score: {(evidence.trust_score_average * 100).toFixed(0)}% (Statutory Allowlist)
                </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Jurisdiction: {evidence.target_jurisdiction}
                </span>
              </div>

              {/* Allowlisted URLs */}
              <div style={{ marginBottom: '16px' }}>
                <label
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    color: 'var(--text-secondary)',
                    textTransform: 'uppercase',
                    display: 'block',
                    marginBottom: '8px',
                  }}
                >
                  Verified Government Portals
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {evidence.official_urls.map((url) => (
                    <a
                      key={url}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="badge badge-accent"
                      style={{ textDecoration: 'none', padding: '6px 10px', fontSize: '0.76rem' }}
                    >
                      <ExternalLink size={12} strokeWidth={1.75} /> {url}
                    </a>
                  ))}
                </div>
              </div>

              {/* Snippets & Evidence */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {evidence.evidence_items.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '12px 14px',
                      backgroundColor: 'var(--bg-sidebar-sand)',
                      border: '1px solid var(--border-default)',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {item.source_name}
                      </span>
                      <span className="badge badge-verified" style={{ fontSize: '0.68rem' }}>
                        Trust: {item.trust_score}
                      </span>
                    </div>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                      {item.snippet}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
              No statutory evidence retrieved yet.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 4: CITIZEN PROFILE FACTS */}
      {activeSubTab === 'profile' && (
        <div>
          {profile ? (
            <div>
              <h4
                style={{
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  color: 'var(--text-secondary)',
                  textTransform: 'uppercase',
                  marginBottom: '10px',
                }}
              >
                Vault Facts & Human Consent Provenance
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '10px' }}>
                {profile.relevant_facts.map((fact) => (
                  <div
                    key={fact.key}
                    style={{
                      padding: '12px 14px',
                      backgroundColor: 'var(--bg-sidebar-sand)',
                      border: `1px solid ${fact.confirmed_by_user ? 'var(--state-verified-border)' : 'var(--state-warning-border)'}`,
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span className="stamped-slip" style={{ fontSize: '0.74rem' }}>
                        {fact.key}
                      </span>
                      <span
                        className={fact.confirmed_by_user ? 'badge badge-verified' : 'badge badge-warning'}
                        style={{ fontSize: '0.66rem' }}
                      >
                        {fact.confirmed_by_user ? 'Verified' : 'Needs Consent'}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)', margin: '4px 0' }}>
                      {fact.value}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Source: {fact.source_ref}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
              No user facts extracted yet.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 5: COMPLIANCE AUDIT */}
      {activeSubTab === 'compliance' && (
        <div>
          {validation ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                <span
                  className={validation.decision === 'approved' ? 'badge badge-verified' : 'badge badge-warning'}
                  style={{ fontSize: '0.8rem' }}
                >
                  Decision: {validation.decision.toUpperCase()}
                </span>
                <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Phase: {validation.phase}
                </span>
              </div>

              <p style={{ fontSize: '0.88rem', color: 'var(--text-primary)', marginBottom: '14px' }}>
                {validation.summary}
              </p>

              {validation.issues && validation.issues.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {validation.issues.map((issue, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '12px 14px',
                        backgroundColor: 'var(--state-danger-bg)',
                        border: '1px solid var(--state-danger-border)',
                        borderRadius: 'var(--radius-sm)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <span className="badge badge-danger" style={{ fontSize: '0.68rem' }}>
                          {issue.severity}
                        </span>
                        <span style={{ fontSize: '0.84rem', fontWeight: 600, color: 'var(--state-danger-text)' }}>
                          Category: {issue.category}
                        </span>
                      </div>
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-primary)', margin: 0 }}>
                        {issue.message}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  style={{
                    padding: '14px 18px',
                    backgroundColor: 'var(--state-verified-bg)',
                    border: '1px solid var(--state-verified-border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--state-verified-text)',
                    fontSize: '0.84rem',
                    fontWeight: 500,
                  }}
                >
                  ✓ All compliance safety checks passed with zero policy violations.
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
              No compliance checks recorded yet.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 6: STATE JSON */}
      {activeSubTab === 'contracts' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Statutory OrchestratorState Data Contract
            </span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(JSON.stringify(state, null, 2));
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="btn-secondary"
              style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            >
              {copied ? <Check size={12} strokeWidth={2} style={{ color: 'var(--state-verified-icon)' }} /> : <Copy size={12} strokeWidth={1.75} />}
              <span>{copied ? 'Copied' : 'Copy State JSON'}</span>
            </button>
          </div>
          <div
            style={{
              backgroundColor: 'var(--bg-stamped-slip)',
              border: '1px dashed var(--border-dashed-slip)',
              borderRadius: 'var(--radius-sm)',
              padding: '14px',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.8rem',
              maxHeight: '400px',
              overflowY: 'auto',
            }}
          >
            <pre>{JSON.stringify(state, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
};
