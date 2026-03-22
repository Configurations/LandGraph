import { useTranslation } from 'react-i18next';
import type { PhaseRunStatus, PhaseStatus } from '../../../api/types';

interface WorkflowPhaseBarProps {
  phases: PhaseStatus[];
  selectedPhaseId: string | null;
  onSelectPhase: (id: string) => void;
  className?: string;
}

const statusBg: Record<PhaseRunStatus, string> = {
  completed: 'bg-accent-green',
  active: 'bg-accent-blue',
  pending: 'bg-surface-tertiary',
  skipped: 'bg-content-quaternary',
};

const statusBorder: Record<PhaseRunStatus, string> = {
  completed: 'border-accent-green',
  active: 'border-accent-blue ring-2 ring-accent-blue/30',
  pending: 'border-border',
  skipped: 'border-content-quaternary',
};

const statusText: Record<PhaseRunStatus, string> = {
  completed: 'text-white',
  active: 'text-white',
  pending: 'text-content-tertiary',
  skipped: 'text-content-quaternary',
};

export function WorkflowPhaseBar({
  phases,
  selectedPhaseId,
  onSelectPhase,
  className = '',
}: WorkflowPhaseBarProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={`flex items-center gap-0 ${className}`}>
      {phases.map((phase, idx) => (
        <div key={phase.id} className="flex items-center">
          {idx > 0 && (
            <div
              className={[
                'h-0.5 w-8',
                phase.status === 'completed' || phase.status === 'active'
                  ? 'bg-accent-green'
                  : 'bg-border',
              ].join(' ')}
            />
          )}
          <button
            onClick={() => onSelectPhase(phase.id)}
            className={[
              'flex items-center justify-center rounded-full border-2 transition-all',
              'h-10 w-10 text-xs font-bold',
              statusBg[phase.status],
              statusBorder[phase.status],
              statusText[phase.status],
              selectedPhaseId === phase.id ? 'scale-110' : 'hover:scale-105',
            ].join(' ')}
            title={t(`workflow.phase_${phase.id}`, { defaultValue: phase.name })}
          >
            {idx + 1}
          </button>
        </div>
      ))}
    </div>
  );
}
