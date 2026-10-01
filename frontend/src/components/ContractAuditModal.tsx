import React, { useState, useEffect } from 'react';
import {
  X,
  FileCheck,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { runContractsCheck } from '../api';

interface ContractAuditModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ContractAuditModal: React.FC<ContractAuditModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  const [auditData, setAuditData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const runAudit = async () => {
    setIsLoading(true);
    try {
      const data = await runContractsCheck();
      setAuditData(data);
    } catch (e) {
      console.error('Audit failed:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    runAudit();
  }, []);

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
                background: 'rgba(56, 189, 248, 0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <FileCheck size={20} color="#38bdf8" />
            </div>
            <div>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                Static Contract & Schema Audit
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Validates Pydantic contracts across all 8 agents against canonical JSON schemas.
              </p>
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
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {auditData?.results?.map((res: any) => (
              <div
                key={res.agent_id}
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
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="badge badge-indigo" style={{ fontSize: '0.65rem' }}>
                      Agent {res.agent_id}
                    </span>
                    <strong style={{ fontSize: '0.88rem', color: '#ffffff' }}>{res.agent_name}</strong>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                    Schema: <code>{res.schema_file}</code>
                  </div>
                </div>

                <span className={res.status === 'OK' ? 'badge badge-emerald' : 'badge badge-rose'} style={{ fontSize: '0.7rem' }}>
                  {res.status === 'OK' ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
                  {res.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px', gap: '10px' }}>
          <button
            onClick={runAudit}
            disabled={isLoading}
            className="btn-secondary"
            style={{ fontSize: '0.8rem' }}
          >
            <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
            Re-run Audit
          </button>
          <button
            onClick={onClose}
            className="btn-primary"
            style={{ fontSize: '0.8rem' }}
          >
            Done
          </button>
        </div>

      </div>
    </div>
  );
};
