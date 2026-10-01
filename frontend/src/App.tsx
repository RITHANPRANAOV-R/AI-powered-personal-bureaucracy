import React, { useState, useEffect, useRef } from 'react';
import { Navbar } from './components/Navbar';
import { GraphVisualizer } from './components/GraphVisualizer';
import { WorkflowLauncher } from './components/WorkflowLauncher';
import { HumanInTheLoopGate } from './components/HumanInTheLoopGate';
import { WorkflowResultsView } from './components/WorkflowResultsView';
import { AlertCircle, X, Shield, Landmark } from 'lucide-react';

import {
  OrchestratorState,
} from './types';
import {
  getHealth,
  startWorkflow,
  submitFactConsent,
  submitAuthorization,
  resumePausedWorkflow,
  abortWorkflow,
  answerClarifications,
  createWorkflowWebSocket,
} from './api';

export function App() {
  const [systemHealth, setSystemHealth] = useState<any>(null);
  const [activeWorkflow, setActiveWorkflow] = useState<OrchestratorState | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  const wsCleanupRef = useRef<(() => void) | null>(null);

  // Initial load
  useEffect(() => {
    getHealth().then(setSystemHealth).catch(() => {});

    const healthInterval = setInterval(() => {
      getHealth().then(setSystemHealth).catch(() => {});
    }, 15000);

    return () => clearInterval(healthInterval);
  }, []);

  // Setup WebSocket when active workflow changes
  useEffect(() => {
    if (!activeWorkflow?.workflow_id) return;

    if (wsCleanupRef.current) {
      wsCleanupRef.current();
      wsCleanupRef.current = null;
    }

    const cleanup = createWorkflowWebSocket(
      activeWorkflow.workflow_id,
      (event, data) => {
        if (data && data.workflow_id === activeWorkflow.workflow_id) {
          setActiveWorkflow(data);
        }
      }
    );
    wsCleanupRef.current = cleanup;

    return () => {
      if (wsCleanupRef.current) {
        wsCleanupRef.current();
        wsCleanupRef.current = null;
      }
    };
  }, [activeWorkflow?.workflow_id]);

  // Handlers
  const handleStartWorkflow = async (params: {
    user_goal: string;
    language: string;
    is_demo: boolean;
    is_dry_run: boolean;
    stop_before_submit: boolean;
  }) => {
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const state = await startWorkflow(params);
      setActiveWorkflow(state);
    } catch (err: any) {
      setErrorBanner(err.message || 'Failed to start workflow');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmitConsent = async (
    decisions: Record<string, 'save' | 'use_once' | 'skip'>,
    answers: Record<string, string>
  ) => {
    if (!activeWorkflow) return;
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const state = await submitFactConsent(activeWorkflow.workflow_id, decisions, answers);
      setActiveWorkflow(state);
    } catch (err: any) {
      setErrorBanner(err.message || 'Consent submission failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmitAuthorization = async (phrase: string) => {
    if (!activeWorkflow) return;
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const state = await submitAuthorization(activeWorkflow.workflow_id, phrase);
      setActiveWorkflow(state);
    } catch (err: any) {
      setErrorBanner(err.message || 'Authorization failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResumePause = async () => {
    if (!activeWorkflow) return;
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const state = await resumePausedWorkflow(activeWorkflow.workflow_id);
      setActiveWorkflow(state);
    } catch (err: any) {
      setErrorBanner(err.message || 'Resume failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAbortWorkflow = async () => {
    if (!activeWorkflow) return;
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const state = await abortWorkflow(activeWorkflow.workflow_id);
      setActiveWorkflow(state);
    } catch (err: any) {
      setErrorBanner(err.message || 'Abort workflow failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmitClarifications = async (answers: Record<string, string>) => {
    if (!activeWorkflow) return;
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const state = await answerClarifications(activeWorkflow.workflow_id, answers);
      setActiveWorkflow(state);
    } catch (err: any) {
      setErrorBanner(err.message || 'Clarifications submission failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewRequest = () => {
    if (activeWorkflow && (activeWorkflow.workflow_status.startsWith('PAUSED_') || activeWorkflow.workflow_status === 'RUNNING')) {
      handleAbortWorkflow();
    }
    setActiveWorkflow(null);
    setErrorBanner(null);
  };

  return (
    <div className="app-root">
      {/* 4-Layer Ambient Page Background */}
      <div className="bg-ambient-washes" aria-hidden="true" />
      <div className="bg-pattern-guilloche" aria-hidden="true" />
      <div className="bg-noise-grain" aria-hidden="true" />

      {/* Masthead Header Band */}
      <Navbar
        systemHealth={systemHealth}
        activeWorkflowId={activeWorkflow?.workflow_id}
        onNewRequest={handleNewRequest}
      />

      {/* Hero / Launcher Section Band */}
      <WorkflowLauncher
        onStartWorkflow={handleStartWorkflow}
        isLoading={isLoading}
      />

      {/* Global Notification Banner */}
      {errorBanner && (
        <div style={{ maxWidth: '1200px', margin: '16px auto 0 auto', padding: '0 20px', width: '100%' }}>
          <div
            className="badge-danger"
            style={{
              padding: '10px 16px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              border: '1px solid var(--state-danger-border)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertCircle size={16} strokeWidth={1.75} />
              <span>{errorBanner}</span>
            </div>
            <button
              onClick={() => setErrorBanner(null)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--state-danger-text)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={15} strokeWidth={2} />
            </button>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <main
        style={{
          flex: 1,
          maxWidth: '1200px',
          width: '100%',
          margin: '24px auto 0 auto',
          paddingBottom: '48px',
        }}
      >
        {/* Dynamic 9-Stage Stepper */}
        {activeWorkflow && (
          <GraphVisualizer
            currentNode={activeWorkflow.current_node || 'START'}
            workflowStatus={activeWorkflow.workflow_status || 'RUNNING'}
          />
        )}

        {/* Human in the loop Gate (AUTHORIZE / CAPTCHA / Consent) */}
        {activeWorkflow && (
          <HumanInTheLoopGate
            state={activeWorkflow}
            onSubmitConsent={handleSubmitConsent}
            onSubmitAuthorization={handleSubmitAuthorization}
            onResumePause={handleResumePause}
            onAbortWorkflow={handleAbortWorkflow}
            onSubmitClarifications={handleSubmitClarifications}
            isLoading={isLoading}
          />
        )}

        {/* Final Confirmation / Citizen Summary View */}
        {activeWorkflow && (
          <WorkflowResultsView state={activeWorkflow} />
        )}
      </main>

      {/* Solid Navy Footer with Amber Rule */}
      <footer
        style={{
          backgroundColor: 'var(--bg-masthead)',
          borderTop: '2px solid var(--border-amber-rule)',
          color: 'var(--text-on-navy)',
          padding: '24px 20px',
          marginTop: 'auto',
          position: 'relative',
          zIndex: 4,
        }}
      >
        <div
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '14px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Landmark size={18} strokeWidth={1.75} style={{ color: '#dce6ef' }} />
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f3efe6', fontFamily: 'var(--font-serif)' }}>
                Civil Services Automated Bureaucracy Architecture
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-on-navy-muted)' }}>
                Statutory Execution Engine • Zero-Trust Citizen Consent Active
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '0.76rem', color: 'var(--text-on-navy-muted)' }}>
            <span className="stamped-slip" style={{ backgroundColor: 'rgba(243, 239, 230, 0.1)', borderColor: 'rgba(243, 239, 230, 0.2)', color: '#f3efe6' }}>
              WCAG 2.1 AA Compliant
            </span>
            <span>Security Protocol SIH-AGY-2026</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
