import React, { useState, useEffect, useRef } from 'react';
import confetti from 'canvas-confetti';
import { Navbar } from './components/Navbar';
import { GraphVisualizer } from './components/GraphVisualizer';
import { WorkflowLauncher } from './components/WorkflowLauncher';
import { HumanInTheLoopGate } from './components/HumanInTheLoopGate';
import { WorkflowResultsView } from './components/WorkflowResultsView';

import {
  OrchestratorState,
  AgentInfo,
  WorkflowTemplate,
} from './types';
import {
  getHealth,
  startWorkflow,
  getWorkflow,
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
          if (data.workflow_status === 'COMPLETED') {
            confetti({ particleCount: 90, spread: 75, origin: { y: 0.6 } });
          }
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
      if (state.workflow_status === 'COMPLETED') {
        confetti({ particleCount: 90, spread: 75, origin: { y: 0.6 } });
      }
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
      if (state.workflow_status === 'COMPLETED') {
        confetti({ particleCount: 90, spread: 75, origin: { y: 0.6 } });
      }
    } catch (err: any) {
      setErrorBanner(err.message || 'Consent failed');
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
      if (state.workflow_status === 'COMPLETED') {
        confetti({ particleCount: 90, spread: 75, origin: { y: 0.6 } });
      }
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
      if (state.workflow_status === 'COMPLETED') {
        confetti({ particleCount: 90, spread: 75, origin: { y: 0.6 } });
      }
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
      if (state.workflow_status === 'COMPLETED') {
        confetti({ particleCount: 90, spread: 75, origin: { y: 0.6 } });
      }
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
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      
      {/* User-focused Top Navigation */}
      <Navbar
        systemHealth={systemHealth}
        activeWorkflowId={activeWorkflow?.workflow_id}
        onNewRequest={handleNewRequest}
      />

      {/* Global Notification Banner */}
      {errorBanner && (
        <div
          className="animate-fade-in"
          style={{
            margin: '0 24px 18px 24px',
            padding: '14px 20px',
            background: 'rgba(244, 63, 94, 0.15)',
            border: '1px solid #f43f5e',
            borderRadius: '12px',
            color: '#fda4af',
            fontSize: '0.9rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>⚠ {errorBanner}</span>
          <button
            onClick={() => setErrorBanner(null)}
            style={{ background: 'transparent', border: 'none', color: '#fda4af', cursor: 'pointer', fontWeight: 700 }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Unified Citizen Workflow Experience */}
      <main style={{ flex: 1, paddingBottom: '40px' }}>
        
        {/* Active Workflow Status & Progress Bar */}
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

        {/* Prompt Input Form */}
        <WorkflowLauncher
          onStartWorkflow={handleStartWorkflow}
          isLoading={isLoading}
        />

        {/* Final Confirmation / Citizen Summary View */}
        {activeWorkflow && (
          <WorkflowResultsView state={activeWorkflow} />
        )}

      </main>
    </div>
  );
}

export default App;
