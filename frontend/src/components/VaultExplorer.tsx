import React, { useState, useEffect } from 'react';
import {
  FolderLock,
  UploadCloud,
  FileText,
  User,
  Save,
  Check,
  Eye,
  RefreshCw,
  HardDrive,
  FileCode,
} from 'lucide-react';
import { VaultFile } from '../types';
import { getVaultFiles, uploadVaultFile, getProfile, updateProfile } from '../api';

export const VaultExplorer: React.FC = () => {
  const [vaultFiles, setVaultFiles] = useState<VaultFile[]>([]);
  const [profileData, setProfileData] = useState<any>({});
  const [profileJsonString, setProfileJsonString] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<VaultFile | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const v = await getVaultFiles();
      setVaultFiles(v.files);
      if (v.files.length > 0 && !selectedFile) {
        setSelectedFile(v.files[0]);
      }

      const p = await getProfile();
      setProfileData(p.profile);
      setProfileJsonString(JSON.stringify(p.profile, null, 2));
    } catch (e) {
      console.error('Error loading vault/profile:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      try {
        await uploadVaultFile(file);
        await loadData();
      } catch (err) {
        alert('File upload failed');
      }
    }
  };

  const handleSaveProfile = async () => {
    try {
      const parsed = JSON.parse(profileJsonString);
      await updateProfile(parsed);
      setSaveStatus('Profile successfully saved!');
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (err: any) {
      alert('Invalid JSON in profile editor: ' + err.message);
    }
  };

  return (
    <div style={{ margin: '0 20px 20px 20px' }}>
      
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            Personal Document Vault & Profile Manager
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Zero-Trust Local Storage: Specialist Agent 2 scans authorized files in <code>data/vault/</code> without cloud uploads.
          </p>
        </div>

        <button
          onClick={loadData}
          disabled={isLoading}
          className="btn-secondary"
          style={{ padding: '8px 14px', fontSize: '0.8rem' }}
        >
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          Refresh Vault
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '20px' }}>
        
        {/* LEFT: VAULT FILES */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FolderLock size={18} color="#38bdf8" />
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                Vault Documents ({vaultFiles.length})
              </h3>
            </div>

            {/* Upload button */}
            <label className="btn-primary" style={{ padding: '6px 12px', fontSize: '0.75rem', cursor: 'pointer' }}>
              <UploadCloud size={14} /> Upload File
              <input type="file" onChange={handleFileUpload} style={{ display: 'none' }} />
            </label>
          </div>

          {/* Files list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
            {vaultFiles.map((file) => {
              const isSelected = selectedFile?.name === file.name;
              return (
                <div
                  key={file.name}
                  onClick={() => setSelectedFile(file)}
                  style={{
                    padding: '10px 14px',
                    borderRadius: '10px',
                    background: isSelected ? 'rgba(99, 102, 241, 0.15)' : 'rgba(5, 7, 12, 0.4)',
                    border: isSelected ? '1px solid #6366f1' : '1px solid var(--border-subtle)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <FileText size={16} color="#818cf8" />
                    <div>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: isSelected ? '#ffffff' : 'var(--text-primary)' }}>
                        {file.name}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        {(file.size_bytes / 1024).toFixed(1)} KB • {file.extension.toUpperCase()}
                      </div>
                    </div>
                  </div>
                  <Eye size={14} color={isSelected ? '#67e8f9' : 'var(--text-muted)'} />
                </div>
              );
            })}
          </div>

          {/* Preview box */}
          {selectedFile && (
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Preview: {selectedFile.name}
              </div>
              <div className="code-box" style={{ maxHeight: '240px', overflowY: 'auto', fontSize: '0.8rem' }}>
                <pre>{selectedFile.preview || '[Empty or binary file]'}</pre>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT: PROFILE JSON EDITOR */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <User size={18} color="#10b981" />
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                Citizen Profile Data (<code>profile.example.json</code>)
              </h3>
            </div>

            <button
              onClick={handleSaveProfile}
              className="btn-accent-emerald"
              style={{ padding: '6px 14px', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Save size={13} /> Save Profile
            </button>
          </div>

          {saveStatus && (
            <div style={{ padding: '8px 12px', background: 'rgba(16, 185, 129, 0.15)', border: '1px solid #10b981', borderRadius: '8px', color: '#6ee7b7', fontSize: '0.8rem', marginBottom: '12px' }}>
              ✓ {saveStatus}
            </div>
          )}

          <textarea
            value={profileJsonString}
            onChange={(e) => setProfileJsonString(e.target.value)}
            rows={18}
            style={{
              width: '100%',
              background: 'rgba(5, 7, 12, 0.8)',
              border: '1px solid var(--border-medium)',
              borderRadius: '10px',
              padding: '12px',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.82rem',
              color: '#e2e8f0',
              outline: 'none',
              resize: 'vertical',
            }}
          />
        </div>

      </div>

    </div>
  );
};
