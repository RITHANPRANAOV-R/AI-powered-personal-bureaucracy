import React, { useState } from 'react';
import {
  FileText,
  CheckCircle2,
  AlertCircle,
  Clock,
  ArrowRight,
  ExternalLink,
  ShieldCheck,
  Download,
  Copy,
  Check,
  Layers,
  Database,
  Search,
  Code2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { OrchestratorState } from '../types';

interface WorkflowResultsViewProps {
  state: OrchestratorState;
}

export const WorkflowResultsView: React.FC<WorkflowResultsViewProps> = ({ state }) => {
  const [activeSubTab, setActiveSubTab] = useState<'response' | 'plan' | 'evidence' | 'profile' | 'compliance' | 'contracts'>('response');
  const [copied, setCopied] = useState(false);

  const citizen = state.citizen_response;
  const plan = state.workflow_plan || state.workflow_plan_original;
  const evidence = state.evidence_result;
  const profile = state.profile_result;
  const validation = state.validation_result;
  const execution = state.execution_result;

  const handleCopyMarkdown = () => {
    if (citizen?.formatted_markdown) {
      navigator.clipboard.writeText(citizen.formatted_markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownloadReport = () => {
    if (!citizen) return;
    const blob = new Blob([citizen.formatted_markdown || citizen.summary], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bureaucracy_report_${state.workflow_id.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="glass-panel" style={{ margin: '0 20px 20px 20px', padding: '24px' }}>
      
      {/* Top Header & Sub-tabs */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '16px', marginBottom: '20px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {citizen?.headline || 'Workflow Inspection & Citizen Guidance'}
            </h3>
            <span className="badge badge-emerald">
              {state.workflow_status}
            </span>
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Goal: "{state.user_goal}"
          </p>
        </div>

        {/* Sub-tab switcher */}
        <div style={{ display: 'flex', gap: '6px', background: 'rgba(5, 7, 12, 0.5)', padding: '4px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
          <button
            onClick={() => setActiveSubTab('response')}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: 'none',
              background: activeSubTab === 'response' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
              color: activeSubTab === 'response' ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            Citizen Guidance
          </button>
          <button
            onClick={() => setActiveSubTab('plan')}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: 'none',
              background: activeSubTab === 'plan' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
              color: activeSubTab === 'plan' ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            DAG Plan ({plan?.steps.length || 0})
          </button>
          <button
            onClick={() => setActiveSubTab('evidence')}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: 'none',
              background: activeSubTab === 'evidence' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
              color: activeSubTab === 'evidence' ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            Official Evidence
          </button>
          <button
            onClick={() => setActiveSubTab('profile')}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: 'none',
              background: activeSubTab === 'profile' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
              color: activeSubTab === 'profile' ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            Facts & Vault
          </button>
          <button
            onClick={() => setActiveSubTab('compliance')}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: 'none',
              background: activeSubTab === 'compliance' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
              color: activeSubTab === 'compliance' ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            Compliance Gates
          </button>
          <button
            onClick={() => setActiveSubTab('contracts')}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: 'none',
              background: activeSubTab === 'contracts' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
              color: activeSubTab === 'contracts' ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            <Code2 size={13} style={{ display: 'inline', marginRight: '4px' }} />
            Raw Contracts
          </button>
        </div>
      </div>

      {/* SUBTAB 1: CITIZEN RESPONSE */}
      {activeSubTab === 'response' && (
        <div className="animate-fade-in">
          {citizen ? (
            <div>
              {/* Executive summary banner */}
              <div style={{ background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', borderRadius: '12px', padding: '18px', marginBottom: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span className="badge badge-indigo" style={{ fontSize: '0.7rem' }}>
                    Executive Citizen Summary
                  </span>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={handleCopyMarkdown}
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.75rem', borderRadius: '6px' }}
                    >
                      {copied ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
                      {copied ? 'Copied' : 'Copy MD'}
                    </button>
                    <button
                      onClick={handleDownloadReport}
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.75rem', borderRadius: '6px' }}
                    >
                      <Download size={13} /> Export Report
                    </button>
                  </div>
                </div>
                <p style={{ fontSize: '0.95rem', color: '#e2e8f0', lineHeight: 1.6 }}>
                  {citizen.summary}
                </p>
              </div>

              {/* Immediate Next Step Card */}
              {citizen.citizen_next_step && (
                <div style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '12px', padding: '18px', marginBottom: '20px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                    <CheckCircle2 size={18} color="#10b981" />
                    <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#6ee7b7' }}>
                      Immediate Citizen Next Step: {citizen.citizen_next_step.title}
                    </h4>
                  </div>
                  <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
                    {citizen.citizen_next_step.description}
                  </p>
                </div>
              )}

              {/* Pending Actions */}
              {citizen.pending_actions && citizen.pending_actions.length > 0 && (
                <div style={{ marginBottom: '20px' }}>
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
                    Pending Actions & Checkpoints
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {citizen.pending_actions.map((pa) => (
                      <div
                        key={pa.step_id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '12px 16px',
                          background: 'rgba(5, 7, 12, 0.6)',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: '10px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span className="badge badge-amber" style={{ fontSize: '0.65rem' }}>
                            {pa.step_id}
                          </span>
                          <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>
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
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
                    Official Markdown Response Document
                  </h4>
                  <div
                    className="code-box"
                    style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, maxHeight: '400px', overflowY: 'auto' }}
                  >
                    {citizen.formatted_markdown}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              Response Generation Agent will compile citizen guidance once the pipeline reaches the RESPONSE node.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 2: DAG PLAN & STEPS */}
      {activeSubTab === 'plan' && (
        <div className="animate-fade-in">
          {plan ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <span className="badge badge-indigo">
                  Service: {plan.service_name} • Task: {plan.task_type}
                </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Total Estimated Time: ~{plan.estimated_total_minutes} mins
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {plan.steps.map((st, i) => (
                  <div
                    key={st.step_id}
                    style={{
                      padding: '14px 18px',
                      borderRadius: '12px',
                      background: 'rgba(5, 7, 12, 0.6)',
                      border: '1px solid var(--border-medium)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '16px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div
                        style={{
                          width: '28px',
                          height: '28px',
                          borderRadius: '8px',
                          background: 'rgba(99, 102, 241, 0.2)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '0.8rem',
                          fontWeight: 700,
                          color: '#a5b4fc',
                        }}
                      >
                        {i + 1}
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                            {st.title}
                          </span>
                          <span className="badge badge-cyan" style={{ fontSize: '0.65rem' }}>
                            {st.actor}
                          </span>
                          {st.requires_user_approval && (
                            <span className="badge badge-amber" style={{ fontSize: '0.65rem' }}>
                              Approval Required
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          {st.description}
                        </p>
                      </div>
                    </div>

                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Clock size={12} /> {st.estimated_minutes}m
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              No workflow plan generated yet.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 3: OFFICIAL RETRIEVED EVIDENCE */}
      {activeSubTab === 'evidence' && (
        <div className="animate-fade-in">
          {evidence ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <span className="badge badge-cyan">
                  Average Trust Score: {(evidence.trust_score_average * 100).toFixed(0)}% (Official Allowlist)
                </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Jurisdiction: {evidence.target_jurisdiction}
                </span>
              </div>

              {/* Official URLs */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>
                  Allowlisted Government Portals
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {evidence.official_urls.map((url) => (
                    <a
                      key={url}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="badge badge-cyan"
                      style={{ textDecoration: 'none', cursor: 'pointer', padding: '6px 12px', fontSize: '0.75rem' }}
                    >
                      <ExternalLink size={12} /> {url}
                    </a>
                  ))}
                </div>
              </div>

              {/* Required Documents Checklist */}
              {evidence.required_documents && evidence.required_documents.length > 0 && (
                <div style={{ marginBottom: '16px' }}>
                  <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>
                    Required Supporting Documents
                  </label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {evidence.required_documents.map((doc, idx) => (
                      <span key={idx} className="badge badge-indigo" style={{ fontSize: '0.75rem' }}>
                        <CheckCircle2 size={12} /> {doc}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Snippets & Evidence Items */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {evidence.evidence_items.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '14px',
                      background: 'rgba(5, 7, 12, 0.6)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '10px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {item.source_name}
                      </span>
                      <span className="badge badge-emerald" style={{ fontSize: '0.65rem' }}>
                        Trust: {item.trust_score}
                      </span>
                    </div>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                      {item.snippet}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              No official evidence retrieved yet.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 4: FACTS & VAULT */}
      {activeSubTab === 'profile' && (
        <div className="animate-fade-in">
          {profile ? (
            <div>
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
                  Extracted Facts & Citizen Provenance
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
                  {profile.relevant_facts.map((fact) => (
                    <div
                      key={fact.key}
                      style={{
                        padding: '12px',
                        background: 'rgba(5, 7, 12, 0.6)',
                        border: `1px solid ${fact.confirmed_by_user ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
                        borderRadius: '10px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <code style={{ fontSize: '0.8rem', color: '#67e8f9' }}>{fact.key}</code>
                        <span className={fact.confirmed_by_user ? 'badge badge-emerald' : 'badge badge-amber'} style={{ fontSize: '0.6rem' }}>
                          {fact.confirmed_by_user ? 'Confirmed' : 'Needs Consent'}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#ffffff', margin: '4px 0' }}>
                        {fact.value}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        Source: {fact.source_ref}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              No user facts extracted yet.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 5: COMPLIANCE GATES */}
      {activeSubTab === 'compliance' && (
        <div className="animate-fade-in">
          {validation ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
                <span className={validation.decision === 'approved' ? 'badge badge-emerald' : 'badge badge-amber'} style={{ fontSize: '0.8rem' }}>
                  Validation Decision: {validation.decision.toUpperCase()}
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  Phase: {validation.phase}
                </span>
              </div>

              <p style={{ fontSize: '0.88rem', color: 'var(--text-primary)', marginBottom: '16px' }}>
                {validation.summary}
              </p>

              {validation.issues && validation.issues.length > 0 ? (
                <div>
                  <h4 style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
                    Flagged Policy / Precondition Issues ({validation.issues.length})
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {validation.issues.map((issue, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: '12px',
                          background: 'rgba(244, 63, 94, 0.08)',
                          border: '1px solid rgba(244, 63, 94, 0.3)',
                          borderRadius: '10px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <span className="badge badge-rose" style={{ fontSize: '0.65rem' }}>
                            {issue.severity}
                          </span>
                          <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#fda4af' }}>
                            Category: {issue.category}
                          </span>
                        </div>
                        <p style={{ fontSize: '0.8rem', color: '#ffffff' }}>
                          {issue.message}
                        </p>
                        {issue.required_resolution && (
                          <div style={{ fontSize: '0.75rem', color: '#fcd34d', marginTop: '4px' }}>
                            Required Resolution: {issue.required_resolution}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div style={{ padding: '16px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: '10px', color: '#6ee7b7', fontSize: '0.85rem' }}>
                  ✓ All compliance safety checks passed with zero policy violations.
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              No compliance checks recorded yet.
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 6: RAW CONTRACTS JSON */}
      {activeSubTab === 'contracts' && (
        <div className="animate-fade-in">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Contract-conforming JSON representation of OrchestratorState
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
              {copied ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
              {copied ? 'Copied' : 'Copy Full State JSON'}
            </button>
          </div>
          <div className="code-box" style={{ maxHeight: '420px', overflowY: 'auto' }}>
            <pre>{JSON.stringify(state, null, 2)}</pre>
          </div>
        </div>
      )}

    </div>
  );
};
