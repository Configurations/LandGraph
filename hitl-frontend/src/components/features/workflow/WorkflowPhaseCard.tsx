import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DeliverablePanel } from './DeliverablePanel';
import type { PhaseDetailResponse } from '../../../api/types';

interface Props {
  phase: PhaseDetailResponse;
  slug: string;
  workflowId: number;
  defaultExpanded?: boolean;
  onRefresh: () => void | Promise<void>;
}

const STATUS_DOT: Record<string, string> = {
  pending: 'bg-gray-400',
  running: 'bg-accent-blue animate-pulse',
  review: 'bg-accent-orange',
  revision: 'bg-accent-blue animate-pulse',
  approved: 'bg-accent-green',
  rejected: 'bg-accent-red',
};

export function WorkflowPhaseCard({ phase, slug, workflowId, defaultExpanded = false, onRefresh }: Props): JSX.Element {
  const { t } = useTranslation();
  const hasProblems = phase.deliverables.some(d => ['rejected', 'revision', 'review'].includes(d.status));
  const isRunning = phase.status === 'running';
  const isPending = phase.status === 'pending';
  const isCompleted = phase.status === 'completed';
  const [expanded, setExpanded] = useState(defaultExpanded || isRunning || hasProblems);
  const [openDeliverableId, setOpenDeliverableId] = useState<number | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const total = phase.deliverables.length;
  const approved = phase.deliverables.filter(d => d.status === 'approved').length;

  const summaryText = phase.status === 'completed'
    ? `${approved}/${total} ${t('workflow.validated')}`
    : phase.status === 'running'
      ? `${approved}/${total} — ${t('workflow.in_progress')}`
      : t('workflow.status_' + phase.status);

  const handleAction = async (action: string) => {
    setActionLoading(action);
    try {
      const { apiFetch } = await import('../../../api/client');
      const base = `/api/projects/${encodeURIComponent(slug)}/workflows/${workflowId}`;

      if (action === 'launch' || action === 'relaunch') {
        if (action === 'relaunch') {
          await apiFetch(`${base}/phases/${phase.id}/reset`, { method: 'POST' });
        }
        await apiFetch(`${base}/phases/${phase.id}/dispatch`, { method: 'POST' });
        // Refresh immediately to show running state
        await onRefresh();
        // Poll until phase is no longer pending (agents dispatched)
        for (let i = 0; i < 6; i++) {
          await new Promise(r => setTimeout(r, 3000));
          await onRefresh();
        }
      } else if (action === 'reset') {
        if (!window.confirm(t('workflow.confirm_reset'))) {
          setActionLoading(null);
          return;
        }
        await apiFetch(`${base}/phases/${phase.id}/reset`, { method: 'POST' });
        await onRefresh();
      } else if (action === 'pause') {
        await apiFetch(`${base}/pause`, { method: 'POST' });
        await onRefresh();
      }
    } catch (err) {
      console.error(`Phase action ${action} failed:`, err);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-surface-primary mb-2">
      {/* Phase header */}
      <div className="flex items-center gap-2 px-4 py-2.5">
        <button
          className="flex items-center gap-2 flex-1 text-left hover:bg-surface-secondary transition-colors rounded"
          onClick={() => setExpanded(!expanded)}
        >
          <span className="text-xs">{expanded ? '\u25bc' : '\u25b6'}</span>
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${phase.status === 'completed' ? 'bg-accent-green' : phase.status === 'running' ? 'bg-accent-blue animate-pulse' : 'bg-gray-400'}`} />
          <span className="font-medium text-sm flex-1">
            {phase.phase_name} <span className="text-content-tertiary font-normal">/ {phase.group_key}</span>
          </span>
          <span className="text-xs text-content-tertiary">{summaryText}</span>
        </button>

        {/* Action buttons */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {isPending && (
            <button
              className="text-xs px-2 py-1 rounded bg-accent-blue text-white hover:bg-accent-blue/80 disabled:opacity-50"
              disabled={actionLoading !== null}
              onClick={() => void handleAction('launch')}
            >
              {actionLoading === 'launch' ? '...' : t('workflow.launch_group')}
            </button>
          )}
          {(isRunning || isCompleted) && (
            <button
              className="text-xs px-2 py-1 rounded bg-accent-orange text-white hover:bg-accent-orange/80 disabled:opacity-50"
              disabled={actionLoading !== null}
              onClick={() => void handleAction('relaunch')}
            >
              {actionLoading === 'relaunch' ? '...' : t('workflow.relaunch_group')}
            </button>
          )}
          {isRunning && (
            <button
              className="text-xs px-2 py-1 rounded bg-gray-500 text-white hover:bg-gray-400 disabled:opacity-50"
              disabled={actionLoading !== null}
              onClick={() => void handleAction('pause')}
            >
              {actionLoading === 'pause' ? '...' : t('workflow.pause_group')}
            </button>
          )}
          {(isRunning || isCompleted) && (
            <button
              className="text-xs px-2 py-1 rounded bg-accent-red/80 text-white hover:bg-accent-red disabled:opacity-50"
              disabled={actionLoading !== null}
              onClick={() => void handleAction('reset')}
            >
              {actionLoading === 'reset' ? '...' : t('workflow.reset_group')}
            </button>
          )}
        </div>
      </div>

      {/* Deliverables list */}
      {expanded && (
        <div className="border-t border-border">
          {phase.deliverables.map((d) => {
            const isOpen = openDeliverableId === d.id;
            return (
              <div key={d.id}>
                {/* Deliverable row */}
                <button
                  className={`w-full flex items-center gap-2 px-6 py-2 text-left text-sm hover:bg-surface-secondary transition-colors ${isOpen ? 'bg-accent-blue/10 border-l-2 border-accent-blue' : ''}`}
                  onClick={() => setOpenDeliverableId(isOpen ? null : d.id)}
                >
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_DOT[d.status] ?? 'bg-gray-400'}`} />
                  <span className="flex-1 truncate">{d.key}</span>
                  <span className="text-xs text-content-tertiary">{d.agent_name || d.agent_id}</span>
                  <span className={`text-xs font-medium ${d.status === 'approved' ? 'text-accent-green' : d.status === 'review' ? 'text-accent-orange' : 'text-content-tertiary'}`}>
                    {d.status}
                  </span>
                  <span className="text-xs">{isOpen ? '\u25b2' : '\u25bc'}</span>
                </button>

                {/* Inline deliverable panel */}
                {isOpen && (
                  <div className="border-t border-border bg-surface-secondary">
                    <DeliverablePanel deliverable={d} onRefresh={onRefresh} />
                  </div>
                )}
              </div>
            );
          })}
          {phase.deliverables.length === 0 && (
            <p className="px-6 py-3 text-xs text-content-tertiary italic">{t('workflow.no_deliverables')}</p>
          )}
        </div>
      )}
    </div>
  );
}
