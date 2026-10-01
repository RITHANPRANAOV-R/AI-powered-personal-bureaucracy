import React, { useState, useEffect } from 'react';
import {
  History,
  ShieldAlert,
  Search,
  RefreshCw,
  Clock,
  Database,
  CheckCircle2,
  AlertTriangle,
  Play,
  Filter,
} from 'lucide-react';
import { AuditLogEntry } from '../types';
import { getAuditLogs, getWorkflows, getWorkflow } from '../api';

interface AuditLogViewerProps {
  onSelectWorkflow: (workflowId: string) => void;
}

export const AuditLogViewer: React.FC<AuditLogViewerProps> = ({ onSelectWorkflow }) => {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [checkpoints, setCheckpoints] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'checkpoints' | 'logs'>('checkpoints');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [l, c] = await Promise.all([getAuditLogs(100), getWorkflows()]);
      setLogs(l.logs);
      setCheckpoints(c.checkpoints);
    } catch (e) {
      console.error('Error loading audit data:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredCheckpoints = checkpoints.filter((ck) =>
    (ck.workflow_id || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    (ck.status || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    (ck.current_node || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredLogs = logs.filter((log) =>
    JSON.stringify(log).toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div style={{ margin: '0 20px 20px 20px' }}>
      
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            Audit Trail & Checkpoint History
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Inspect cryptographic audit logs and resume past workflows stored in local SQLite database.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Sub-tab switcher */}
          <div style={{ display: 'flex', gap: '4px', background: 'rgba(5, 7, 12, 0.5)', padding: '4px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
            <button
              onClick={() => setActiveTab('checkpoints')}
              style={{
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                border: 'none',
                background: activeTab === 'checkpoints' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
                color: activeTab === 'checkpoints' ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              SQLite Checkpoints ({checkpoints.length})
            </button>
            <button
              onClick={() => setActiveTab('logs')}
              style={{
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                border: 'none',
                background: activeTab === 'logs' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
                color: activeTab === 'logs' ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              Audit Log Lines ({logs.length})
            </button>
          </div>

          <button
            onClick={loadData}
            disabled={isLoading}
            className="btn-secondary"
            style={{ padding: '8px 14px', fontSize: '0.8rem' }}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Search Filter */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(5, 7, 12, 0.6)', border: '1px solid var(--border-medium)', borderRadius: '10px', padding: '8px 14px', maxWidth: '400px' }}>
          <Search size={16} color="var(--text-muted)" style={{ marginRight: '8px' }} />
          <input
            type="text"
            placeholder="Search by workflow ID, status, or keyword..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ background: 'transparent', border: 'none', color: '#ffffff', fontSize: '0.85rem', width: '100%', outline: 'none' }}
          />
        </div>
      </div>

      {/* TAB 1: CHECKPOINTS */}
      {activeTab === 'checkpoints' && (
        <div className="glass-panel" style={{ padding: '16px', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-medium)', textAlign: 'left', color: 'var(--text-muted)' }}>
                <th style={{ padding: '10px' }}>Workflow ID</th>
                <th style={{ padding: '10px' }}>Node</th>
                <th style={{ padding: '10px' }}>Status</th>
                <th style={{ padding: '10px' }}>Updated At</th>
                <th style={{ padding: '10px', textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredCheckpoints.map((ck) => (
                <tr key={ck.workflow_id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '12px 10px', fontFamily: 'var(--font-mono)', color: '#67e8f9', fontWeight: 600 }}>
                    {ck.workflow_id}
                  </td>
                  <td style={{ padding: '12px 10px' }}>
                    <span className="badge badge-indigo" style={{ fontSize: '0.65rem' }}>
                      {ck.current_node}
                    </span>
                  </td>
                  <td style={{ padding: '12px 10px' }}>
                    <span className={ck.status === 'COMPLETED' ? 'badge badge-emerald' : ck.status.startsWith('PAUSED_') ? 'badge badge-amber' : 'badge badge-rose'} style={{ fontSize: '0.65rem' }}>
                      {ck.status}
                    </span>
                  </td>
                  <td style={{ padding: '12px 10px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                    {new Date(ck.updated_at).toLocaleString()}
                  </td>
                  <td style={{ padding: '12px 10px', textAlign: 'right' }}>
                    <button
                      onClick={() => onSelectWorkflow(ck.workflow_id)}
                      className="btn-primary"
                      style={{ padding: '4px 12px', fontSize: '0.75rem' }}
                    >
                      Inspect / Resume
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 2: AUDIT LOG LINES */}
      {activeTab === 'logs' && (
        <div className="glass-panel" style={{ padding: '16px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {filteredLogs.map((log, idx) => (
              <div
                key={idx}
                style={{
                  padding: '12px 14px',
                  borderRadius: '8px',
                  background: 'rgba(5, 7, 12, 0.7)',
                  border: '1px solid var(--border-subtle)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.78rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: '#a5b4fc', fontWeight: 600 }}>
                    {log.event_type || log.action || 'AUDIT_EVENT'}
                  </span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>
                    {log.timestamp || 'N/A'}
                  </span>
                </div>
                <div style={{ color: '#cbd5e1', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {JSON.stringify(log, null, 2)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
};
