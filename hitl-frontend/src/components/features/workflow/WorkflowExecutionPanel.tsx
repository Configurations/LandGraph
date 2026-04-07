import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { Spinner } from '../../ui/Spinner';
import { WorkflowPhaseCard } from './WorkflowPhaseCard';
import { HumanGateBanner } from './HumanGateBanner';
import { apiFetch } from '../../../api/client';
import * as workflowApi from '../../../api/workflow';
import type {
  ProjectWorkflowResponse,
  WorkflowPhasesResponse,
} from '../../../api/types';

interface Props {
  slug: string;
  workflows: ProjectWorkflowResponse[];
  onRefreshWorkflows: () => void;
}


export function WorkflowExecutionPanel({ slug, workflows: workflowsProp, onRefreshWorkflows }: Props): JSX.Element {
  const { t } = useTranslation();
  const [localWorkflows, setLocalWorkflows] = useState(workflowsProp);
  const [activePhases, setActivePhases] = useState<Record<number, WorkflowPhasesResponse>>({});
  const [loadingIds, setLoadingIds] = useState<Set<number>>(new Set());
  const [startingId, setStartingId] = useState<number | null>(null);

  // Sync from parent when prop changes
  useEffect(() => {
    setLocalWorkflows(workflowsProp);
  }, [workflowsProp]);

  const activeWorkflows = localWorkflows.filter(w => w.status === 'active');
  const launchableWorkflows = localWorkflows.filter(w => ['pending', 'paused'].includes(w.status));

  // Load phases for all active workflows
  const loadActivePhases = useCallback(async () => {
    for (const wf of activeWorkflows) {
      setLoadingIds(prev => new Set([...prev, wf.id]));
      try {
        const data = await workflowApi.getWorkflowPhases(slug, wf.id);
        setActivePhases(prev => ({ ...prev, [wf.id]: data }));
      } catch {
        // ignore
      } finally {
        setLoadingIds(prev => { const next = new Set(prev); next.delete(wf.id); return next; });
      }
    }
  }, [slug, activeWorkflows.map(w => w.id).join(',')]);

  useEffect(() => {
    void loadActivePhases();
  }, [loadActivePhases]);

  // Poll every 10s when any deliverable is running
  useEffect(() => {
    const hasRunning = Object.values(activePhases).some(wp =>
      wp.phases.some(p => p.deliverables.some(d => d.status === 'running')),
    );
    if (!hasRunning) return;
    const timer = setInterval(() => void loadActivePhases(), 10_000);
    return () => clearInterval(timer);
  }, [activePhases, loadActivePhases]);

  const handleStart = useCallback(async (wfId: number) => {
    setStartingId(wfId);
    try {
      await workflowApi.startWorkflow(slug, wfId);
    } catch (err) {
      console.error('startWorkflow failed:', err);
      setStartingId(null);
      return;
    }
    // Update local state immediately — mark workflow as active
    setLocalWorkflows(prev => prev.map(w => w.id === wfId ? { ...w, status: 'active' as const } : w));
    // Load phases for the just-started workflow
    try {
      const data = await workflowApi.getWorkflowPhases(slug, wfId);
      setActivePhases(prev => ({ ...prev, [wfId]: data }));
    } catch (err) {
      console.error('getWorkflowPhases failed:', err);
    }
    // Also notify parent in background
    onRefreshWorkflows();
    setStartingId(null);
  }, [slug, onRefreshWorkflows]);

  const handleGateRespond = useCallback(async (wfId: number, gateId: string, response: string) => {
    await apiFetch(`/api/projects/${encodeURIComponent(slug)}/analysis/reply`, {
      method: 'POST',
      body: JSON.stringify({ request_id: gateId, response }),
    });
    try {
      const data = await workflowApi.getWorkflowPhases(slug, wfId);
      setActivePhases(prev => ({ ...prev, [wfId]: data }));
    } catch {
      // ignore
    }
  }, [slug]);

  const handleRefreshOne = useCallback(async (wfId: number) => {
    try {
      const data = await workflowApi.getWorkflowPhases(slug, wfId);
      setActivePhases(prev => ({ ...prev, [wfId]: data }));
    } catch {
      // ignore
    }
  }, [slug]);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Launch bar */}
      {launchableWorkflows.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4 flex-shrink-0">
          {launchableWorkflows.map(wf => {
            const isWaiting = wf.status === 'pending' && wf.depends_on_workflow_id != null;
            return (
              <div key={wf.id} className="flex items-center gap-2 rounded-lg border border-border bg-surface-primary px-3 py-1.5">
                <span className="text-sm font-medium">{wf.workflow_name}</span>
                {isWaiting && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-accent-orange/15 text-accent-orange">{t('workflow.status_pending')}</span>
                )}
                <Button
                  size="sm"
                  onClick={() => void handleStart(wf.id)}
                  loading={startingId === wf.id}
                  disabled={isWaiting}
                >
                  {t('workflow.start')}
                </Button>
              </div>
            );
          })}
        </div>
      )}

      {/* Workflows with phases to show: active from props + any with loaded phases */}
      {(() => {
        const shownIds = new Set<number>();
        activeWorkflows.forEach(w => shownIds.add(w.id));
        Object.keys(activePhases).forEach(k => shownIds.add(Number(k)));
        const shownWorkflows = localWorkflows.filter(w => shownIds.has(w.id));

        if (shownWorkflows.length === 0 && launchableWorkflows.length === 0) {
          return <p className="text-sm text-content-tertiary text-center py-8">{t('workflow.no_phases')}</p>;
        }
        if (shownWorkflows.length === 0) {
          return <p className="text-sm text-content-tertiary text-center py-8">{t('workflow.click_start')}</p>;
        }

        return shownWorkflows.map(wf => {
        const phases = activePhases[wf.id];
        const isLoading = loadingIds.has(wf.id);

        return (
          <div key={wf.id} className="mb-6">
            {/* Workflow header */}
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2 h-2 rounded-full bg-accent-blue animate-pulse" />
              <span className="text-sm font-semibold flex-1">{wf.workflow_name}</span>
              <button
                className="text-xs text-content-tertiary hover:text-content-primary"
                onClick={() => void handleRefreshOne(wf.id)}
              >
                {t('common.refresh')}
              </button>
            </div>

            {/* Human gate */}
            {phases?.human_gate && (
              <HumanGateBanner
                gate={phases.human_gate}
                onRespond={(response) => handleGateRespond(wf.id, phases.human_gate!.id, response)}
              />
            )}

            {/* Phases */}
            {isLoading && (
              <div className="flex items-center justify-center py-4">
                <Spinner size="sm" />
              </div>
            )}

            {!isLoading && phases && phases.phases.map((phase, idx) => (
              <WorkflowPhaseCard
                key={phase.id}
                phase={phase}
                slug={slug}
                workflowId={wf.id}
                defaultExpanded={idx === 0}
                onRefresh={() => void handleRefreshOne(wf.id)}
              />
            ))}

            {!isLoading && phases && phases.phases.length === 0 && (
              <p className="text-xs text-content-tertiary italic pl-4">{t('workflow.no_phases')}</p>
            )}
          </div>
        );
      });
      })()}
    </div>
  );
}
