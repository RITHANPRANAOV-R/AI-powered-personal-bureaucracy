import React, { useState } from 'react';
import {
  Sparkles,
  Play,
  Shield,
  Sliders,
  Globe,
  CheckCircle2,
  AlertCircle,
  Command,
  ArrowRight,
  ShieldCheck,
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
    <div className="glass-panel" style={{ padding: '28px', margin: '0 20px 24px 20px', position: 'relative', overflow: 'hidden' }}>
      {/* Subtle top accent gradient line */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '3px',
          background: 'linear-gradient(90deg, #6366f1, #06b6d4, #10b981)',
        }}
      />

      {/* Header section */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '22px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                background: 'rgba(99, 102, 241, 0.2)',
                border: '1px solid rgba(99, 102, 241, 0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Sparkles size={20} color="#818cf8" />
            </div>
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
                AI Bureaucracy Assistant
              </h2>
              <span style={{ fontSize: '0.75rem', color: '#a5b4fc', fontWeight: 600 }}>
                Autonomous Government Workflow & Form Execution Engine
              </span>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="badge badge-emerald" style={{ fontSize: '0.72rem', padding: '6px 12px' }}>
            <ShieldCheck size={13} /> 8 Specialist Agents Active
          </div>

          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="btn-secondary"
            style={{ padding: '7px 14px', fontSize: '0.8rem', borderRadius: '10px' }}
          >
            <Sliders size={14} color="var(--accent-cyan)" />
            {showAdvanced ? 'Hide Options' : 'Execution Options'}
          </button>
        </div>
      </div>

      {/* Main Goal Form */}
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span>Enter Citizen Request / Goal:</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500 }}>
              Natural language instructions for government portal execution
            </span>
          </label>

          <div style={{ position: 'relative' }}>
            <textarea
              rows={3}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="Type your official bureaucracy request here (e.g. 'Submit an RTI Online request to Ministry of External Affairs regarding passport dispatch timeline' or 'Update address in Aadhaar')..."
              style={{
                width: '100%',
                background: 'rgba(5, 7, 14, 0.85)',
                border: '1px solid var(--border-medium)',
                borderRadius: '14px',
                padding: '16px 18px',
                color: '#ffffff',
                fontSize: '0.96rem',
                lineHeight: '1.5',
                outline: 'none',
                resize: 'vertical',
                minHeight: '88px',
                fontFamily: 'var(--font-sans)',
                boxShadow: 'inset 0 2px 6px rgba(0, 0, 0, 0.4)',
                transition: 'border-color 0.2s, box-shadow 0.2s',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = 'rgba(99, 102, 241, 0.7)';
                e.target.style.boxShadow = '0 0 0 3px rgba(99, 102, 241, 0.2), inset 0 2px 6px rgba(0,0,0,0.4)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'var(--border-medium)';
                e.target.style.boxShadow = 'inset 0 2px 6px rgba(0, 0, 0, 0.4)';
              }}
            />
          </div>
        </div>

        {/* Suggestion Chips */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '18px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
            Suggestions:
          </span>
          {POPULAR_PROMPTS.map((p, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSelectPrompt(p)}
              style={{
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-secondary)',
                borderRadius: '8px',
                padding: '4px 10px',
                fontSize: '0.75rem',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(99, 102, 241, 0.15)';
                e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.35)';
                e.currentTarget.style.color = '#c7d2fe';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)';
                e.currentTarget.style.borderColor = 'var(--border-subtle)';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
            >
              {p.length > 55 ? `${p.slice(0, 52)}...` : p}
            </button>
          ))}
        </div>

        {/* Advanced Options Bar */}
        {showAdvanced && (
          <div
            className="animate-fade-in"
            style={{
              padding: '16px',
              background: 'rgba(5, 7, 14, 0.6)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '12px',
              marginBottom: '18px',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '16px',
            }}
          >
            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>
                Response Language
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                style={{
                  width: '100%',
                  background: 'rgba(16, 21, 34, 0.9)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#ffffff',
                  fontSize: '0.85rem',
                  outline: 'none',
                }}
              >
                <option value="en">English (Official)</option>
                <option value="hi">हिन्दी (Hindi)</option>
                <option value="ta">தமிழ் (Tamil)</option>
                <option value="te">తెలుగు (Telugu)</option>
                <option value="bn">বাংলা (Bengali)</option>
                <option value="mr">मराठी (Marathi)</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>
                Execution Mode
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', height: '38px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={isDryRun}
                    onChange={(e) => setIsDryRun(e.target.checked)}
                    style={{ accentColor: '#6366f1' }}
                  />
                  Dry Run (Inspection Only)
                </label>
              </div>
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>
                Submission Gate
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', height: '38px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={stopBeforeSubmit}
                    onChange={(e) => setStopBeforeSubmit(e.target.checked)}
                    style={{ accentColor: '#6366f1' }}
                  />
                  Pause Before Final Submit
                </label>
              </div>
            </div>
          </div>
        )}

        {/* Action Row */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '12px' }}>
          <button
            type="submit"
            disabled={isLoading || !goal.trim()}
            className="btn-primary"
            style={{
              padding: '12px 28px',
              fontSize: '0.95rem',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              borderRadius: '12px',
              boxShadow: '0 4px 20px rgba(99, 102, 241, 0.4)',
            }}
          >
            {isLoading ? (
              <>
                <div className="spinner" style={{ width: '16px', height: '16px' }} />
                <span>Agents Orchestrating...</span>
              </>
            ) : (
              <>
                <Play size={18} />
                <span>Start Agent Workflow</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
