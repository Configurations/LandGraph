import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { ProjectWorkflowResponse, ProjectWorkflowStatus } from '../../../api/types';

interface WorkflowSelectorProps {
  workflows: ProjectWorkflowResponse[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  className?: string;
}

const statusColor: Record<ProjectWorkflowStatus, 'blue' | 'green' | 'orange' | 'purple'> = {
  draft: 'purple',
  active: 'blue',
  paused: 'orange',
  completed: 'green',
};

export function WorkflowSelector({
  workflows,
  selectedId,
  onSelect,
  className = '',
}: WorkflowSelectorProps): JSX.Element {
  const { t } = useTranslation();

  if (workflows.length === 0) {
    return (
      <p className={`text-sm text-content-tertiary ${className}`}>
        {t('multi_workflow.no_workflows')}
      </p>
    );
  }

  return (
    <div className={`flex gap-1 overflow-x-auto ${className}`}>
      {workflows.map((wf) => (
        <button
          key={wf.id}
          onClick={() => onSelect(wf.id)}
          className={[
            'flex items-center gap-2 whitespace-nowrap px-3 py-2 rounded-lg text-sm transition-colors',
            selectedId === wf.id
              ? 'bg-accent-blue/10 text-accent-blue font-medium'
              : 'bg-surface-tertiary text-content-secondary hover:bg-surface-hover',
          ].join(' ')}
        >
          <span>{wf.name}</span>
          <Badge color={statusColor[wf.status]} size="sm" variant="status">
            {t(`multi_workflow.status_${wf.status}`)}
          </Badge>
        </button>
      ))}
    </div>
  );
}
