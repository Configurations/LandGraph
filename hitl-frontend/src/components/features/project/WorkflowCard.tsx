import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import { Button } from '../../ui/Button';
import type { ProjectWorkflowResponse, ProjectWorkflowStatus } from '../../../api/types';

interface WorkflowCardProps {
  workflow: ProjectWorkflowResponse;
  onActivate?: (id: string) => void;
  onPause?: (id: string) => void;
  onComplete?: (id: string) => void;
  onRelaunch?: (id: string) => void;
  className?: string;
}

const statusColor: Record<ProjectWorkflowStatus, 'blue' | 'green' | 'orange' | 'purple'> = {
  draft: 'purple',
  active: 'blue',
  paused: 'orange',
  completed: 'green',
};

export function WorkflowCard({
  workflow,
  onActivate,
  onPause,
  onComplete,
  onRelaunch,
  className = '',
}: WorkflowCardProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div
      className={[
        'flex flex-col gap-3 rounded-xl border border-border bg-surface-secondary p-4',
        className,
      ].join(' ')}
    >
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-content-primary">{workflow.name}</h4>
        <Badge color={statusColor[workflow.status]} variant="status" size="sm">
          {t(`multi_workflow.status_${workflow.status}`)}
        </Badge>
      </div>

      <div className="flex items-center gap-2">
        <Badge color="purple" size="sm">{workflow.type}</Badge>
        <Badge color="blue" size="sm">
          {t(`multi_workflow.mode_${workflow.mode}`)}
        </Badge>
      </div>

      <div className="w-full bg-surface-tertiary rounded-full h-1.5">
        <div
          className="bg-accent-blue h-1.5 rounded-full transition-all"
          style={{ width: `${Math.min(workflow.progress, 100)}%` }}
        />
      </div>
      <span className="text-xs text-content-tertiary">
        {t('multi_workflow.progress_label', { value: workflow.progress })}
      </span>

      <div className="flex gap-2 mt-auto">
        {workflow.status === 'draft' && onActivate && (
          <Button variant="primary" size="sm" onClick={() => onActivate(workflow.id)}>
            {t('multi_workflow.activate')}
          </Button>
        )}
        {workflow.status === 'active' && onPause && (
          <Button variant="secondary" size="sm" onClick={() => onPause(workflow.id)}>
            {t('multi_workflow.pause')}
          </Button>
        )}
        {workflow.status === 'active' && onComplete && (
          <Button variant="primary" size="sm" onClick={() => onComplete(workflow.id)}>
            {t('multi_workflow.complete')}
          </Button>
        )}
        {(workflow.status === 'paused' || workflow.status === 'completed') && onRelaunch && (
          <Button variant="ghost" size="sm" onClick={() => onRelaunch(workflow.id)}>
            {t('multi_workflow.relaunch')}
          </Button>
        )}
      </div>
    </div>
  );
}
