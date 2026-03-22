import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import { WorkflowAgentCard } from './WorkflowAgentCard';
import { WorkflowDeliverableRow } from './WorkflowDeliverableRow';
import type { PhaseRunStatus, PhaseStatus } from '../../../api/types';

interface WorkflowPhaseDetailProps {
  phase: PhaseStatus;
  onAgentClick?: (agentId: string) => void;
  className?: string;
}

const statusColor: Record<PhaseRunStatus, 'green' | 'blue' | 'orange' | 'red'> = {
  completed: 'green',
  active: 'blue',
  pending: 'orange',
  skipped: 'red',
};

export function WorkflowPhaseDetail({
  phase,
  onAgentClick,
  className = '',
}: WorkflowPhaseDetailProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      <div className="flex items-center gap-2">
        <h3 className="text-lg font-semibold text-content-primary">
          {t(`workflow.phase_${phase.id}`, { defaultValue: phase.name })}
        </h3>
        <Badge size="md" color={statusColor[phase.status]}>
          {t(`workflow.phase_status_${phase.status}`)}
        </Badge>
      </div>

      {phase.agents.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-widest text-content-quaternary mb-2">
            {t('workflow.agents')}
          </h4>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
            {phase.agents.map((agent) => (
              <WorkflowAgentCard
                key={agent.agent_id}
                agent={agent}
                onClick={onAgentClick ? () => onAgentClick(agent.agent_id) : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {phase.deliverables.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-widest text-content-quaternary mb-2">
            {t('workflow.deliverables')}
          </h4>
          <div className="flex flex-col gap-1">
            {phase.deliverables.map((d) => (
              <WorkflowDeliverableRow key={d.key} deliverable={d} />
            ))}
          </div>
        </div>
      )}

      {phase.agents.length === 0 && phase.deliverables.length === 0 && (
        <p className="text-sm text-content-tertiary">{t('workflow.no_content')}</p>
      )}
    </div>
  );
}
