import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DeliverablePanel } from './DeliverablePanel';
import type { PhaseDetailResponse } from '../../../api/types';

interface Props {
  phase: PhaseDetailResponse;
  defaultExpanded?: boolean;
  onRefresh: () => void;
}

const STATUS_DOT: Record<string, string> = {
  pending: 'bg-gray-400',
  running: 'bg-accent-blue animate-pulse',
  review: 'bg-accent-orange',
  revision: 'bg-accent-blue animate-pulse',
  approved: 'bg-accent-green',
  rejected: 'bg-accent-red',
};

export function WorkflowPhaseCard({ phase, defaultExpanded = false, onRefresh }: Props): JSX.Element {
  const { t } = useTranslation();
  const hasProblems = phase.deliverables.some(d => ['rejected', 'revision', 'review'].includes(d.status));
  const isRunning = phase.status === 'running';
  const [expanded, setExpanded] = useState(defaultExpanded || isRunning || hasProblems);
  const [openDeliverableId, setOpenDeliverableId] = useState<number | null>(null);

  const total = phase.deliverables.length;
  const approved = phase.deliverables.filter(d => d.status === 'approved').length;

  const summaryText = phase.status === 'completed'
    ? `${approved}/${total} ${t('workflow.validated')}`
    : phase.status === 'running'
      ? `${approved}/${total} — ${t('workflow.in_progress')}`
      : t('workflow.status_' + phase.status);

  return (
    <div className="rounded-lg border border-border bg-surface-primary mb-2">
      {/* Phase header */}
      <button
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-surface-secondary transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-xs">{expanded ? '\u25bc' : '\u25b6'}</span>
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${phase.status === 'completed' ? 'bg-accent-green' : phase.status === 'running' ? 'bg-accent-blue animate-pulse' : 'bg-gray-400'}`} />
        <span className="font-medium text-sm flex-1">
          {phase.phase_name} <span className="text-content-tertiary font-normal">/ {phase.group_key}</span>
        </span>
        <span className="text-xs text-content-tertiary">{summaryText}</span>
      </button>

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
