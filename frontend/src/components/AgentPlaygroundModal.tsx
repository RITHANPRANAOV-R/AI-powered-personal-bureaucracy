import React, { useState } from 'react';
import {
  X,
  Play,
  Bot,
  FileCode,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
} from 'lucide-react';
import { AgentInfo } from '../types';
import { directRunAgent } from '../api';

interface AgentPlaygroundModalProps {
  agent: AgentInfo | null;
  onClose: () => void;
}

export const AgentPlaygroundModal: React.FC<AgentPlaygroundModalProps> = ({ agent, onClose }) => {
  if (!agent) return null;

  const getDefaultPayload = (id: number) => {
    switch (id) {
      case 1:
        return JSON.stringify({ user_goal: 'I need to apply for a fresh tatkaal passport on Passport Seva', language_preference: 'en' }, null, 2);
      case 2:
        return JSON.stringify({ vault_dir: 'data/vault', profile_path: 'data/profile.example.json', purpose: 'Passport Application' }, null, 2);
      case 3:
        return JSON.stringify({ service_name: 'Passport Seva', target_jurisdiction: 'India', user_goal: 'Passport registration requirements' }, null, 2);
      case 4:
        return JSON.stringify({ service_name: 'Passport Seva', task_type: 'register', user_goal: 'Register for new passport' }, null, 2);
      case 8:
        return JSON.stringify({ user_goal: 'Register on Passport Seva for online passport submission' }, null, 2);
      default:
        return JSON.stringify({ user_goal: 'Sample test input' }, null, 2);
    }
  };

  const [payloadString, setPayloadString] = useState(() => getDefaultPayload(agent.id));
  const [result, setResult] = useState<any>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    setResult(null);
    try {
      const parsed = JSON.parse(payloadString);
      const res = await directRunAgent(agent.id, parsed);
      setResult(res.result);
    } catch (err: any) {
      setError(err.message || 'Execution error');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(5, 7, 12, 0.85)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '20px',
      }}
    >
      <div
        className="glass-panel-elevated animate-fade-in"
        style={{
          width: '100%',
          maxWidth: '750px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                background: 'rgba(99, 102, 241, 0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Bot size={20} color="#818cf8" />
            </div>
            <div>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                {agent.name} — Direct Sandbox Test
              </h3>
              <span className="badge badge-indigo" style={{ fontSize: '0.65rem' }}>
                Contract: {agent.contract}
              </span>
            </div>
          </div>

          <button
            onClick={onClose}
            className="btn-secondary"
            style={{ padding: '6px', borderRadius: '8px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Input JSON */}
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>
              Input Payload (JSON)
            </label>
            <textarea
              rows={6}
              value={payloadString}
              onChange={(e) => setPayloadString(e.target.value)}
              style={{
                width: '100%',
                background: 'rgba(5, 7, 12, 0.8)',
                border: '1px solid var(--border-medium)',
                borderRadius: '8px',
                padding: '10px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.82rem',
                color: '#e2e8f0',
                outline: 'none',
              }}
            />
          </div>

          {/* Action button */}
          <div>
            <button
              onClick={handleRun}
              disabled={isRunning}
              className="btn-primary"
              style={{ width: '100%', padding: '10px' }}
            >
              {isRunning ? (
                <>
                  <div className="pulse-dot" style={{ background: '#ffffff' }} />
                  Executing Specialist Agent in Isolation...
                </>
              ) : (
                <>
                  <Play size={16} /> Execute Agent
                </>
              )}
            </button>
          </div>

          {/* Error Banner */}
          {error && (
            <div style={{ padding: '12px', background: 'rgba(244, 63, 94, 0.15)', border: '1px solid #f43f5e', borderRadius: '8px', color: '#fda4af', fontSize: '0.85rem' }}>
              <AlertCircle size={16} style={{ display: 'inline', marginRight: '6px' }} />
              {error}
            </div>
          )}

          {/* Result */}
          {result && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span className="badge badge-emerald" style={{ fontSize: '0.7rem' }}>
                  ✓ Validated Contract Output
                </span>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  }}
                  className="btn-secondary"
                  style={{ padding: '4px 8px', fontSize: '0.7rem' }}
                >
                  {copied ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div className="code-box" style={{ maxHeight: '250px', overflowY: 'auto' }}>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  );
};
