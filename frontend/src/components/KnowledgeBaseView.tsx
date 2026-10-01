import React, { useState, useEffect } from 'react';
import {
  Globe,
  ShieldCheck,
  ExternalLink,
  Lock,
  CheckCircle2,
  RefreshCw,
  Server,
  BookOpen,
} from 'lucide-react';
import { getKnowledgeBase } from '../api';

export const KnowledgeBaseView: React.FC = () => {
  const [kbData, setKbData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const loadKb = async () => {
    setIsLoading(true);
    try {
      const data = await getKnowledgeBase();
      setKbData(data);
    } catch (e) {
      console.error('Error loading KB:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadKb();
  }, []);

  return (
    <div style={{ margin: '0 20px 20px 20px' }}>
      
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            Official Government Knowledge Base & Allowlist
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Agent 3 strictly confines retrieval to allowlisted government endpoints with 1.00 cryptographic trust scores.
          </p>
        </div>

        <button
          onClick={loadKb}
          disabled={isLoading}
          className="btn-secondary"
          style={{ padding: '8px 14px', fontSize: '0.8rem' }}
        >
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          Refresh Registry
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px' }}>
        
        {/* OFFICIAL SOURCES MANIFEST */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <BookOpen size={18} color="#67e8f9" />
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              Verified Knowledge Base Sources
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {kbData?.sources?.map((src: any, idx: number) => (
              <div
                key={idx}
                style={{
                  padding: '16px',
                  borderRadius: '12px',
                  background: 'rgba(5, 7, 12, 0.5)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#ffffff' }}>
                    {src.title}
                  </h4>
                  <span className="badge badge-emerald" style={{ fontSize: '0.65rem' }}>
                    Trust Score: {src.trust_score * 100}%
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <Globe size={13} color="#38bdf8" />
                  <a
                    href={src.canonical_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: '0.8rem', color: '#38bdf8', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    {src.canonical_url} <ExternalLink size={11} />
                  </a>
                </div>

                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Service: <strong style={{ color: '#e2e8f0' }}>{src.service_name}</strong> • Domain: <code>{src.domain}</code>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ALLOWLISTED HOST DOMAINS */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <ShieldCheck size={18} color="#10b981" />
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              Allowlisted Government Domain Registry
            </h3>
          </div>

          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '14px' }}>
            Network security policy strictly blocks outbound web scraping to domains outside this vetted registry:
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {(kbData?.allowed_hosts || ['passportindia.gov.in', 'rtionline.gov.in', 'uidai.gov.in', 'nvsp.in', 'digilocker.gov.in', 'parivahan.gov.in']).map((host: string) => (
              <div
                key={host}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  background: 'rgba(5, 7, 12, 0.4)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Lock size={14} color="#10b981" />
                  <code style={{ fontSize: '0.85rem', color: '#6ee7b7' }}>{host}</code>
                </div>
                <span className="badge badge-emerald" style={{ fontSize: '0.6rem' }}>
                  ALLOWLISTED
                </span>
              </div>
            ))}
          </div>
        </div>

      </div>

    </div>
  );
};
