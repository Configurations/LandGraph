import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { ProjectWorkflowResponse, ProjectWorkflowStatus } from '../../../api/types';

interface WorkflowTimelineProps {
  workflows: ProjectWorkflowResponse[];
  className?: string;
}

const statusColor: Record<ProjectWorkflowStatus, 'blue' | 'green' | 'orange' | 'purple'> = {
  pending: 'purple',
  active: 'blue',
  paused: 'orange',
  completed: 'green',
  cancelled: 'orange',
};

const statusDot: Record<ProjectWorkflowStatus, string> = {
  pending: 'bg-accent-purple',
  active: 'bg-accent-blue',
  paused: 'bg-accent-orange',
  completed: 'bg-accent-green',
  cancelled: 'bg-accent-orange',
};

export function WorkflowTimeline({
  workflows,
  className = '',
}: WorkflowTimelineProps): JSX.Element {
  const { t } = useTranslation();

  if (workflows.length === 0) {
    return (
      <p className={`text-sm text-content-tertiary ${className}`}>
        {t('multi_workflow.no_workflows')}
      </p>
    );
  }

  return (
    <div className={`relative flex flex-col gap-0 ${className}`}>
      {workflows.map((wf, idx) => {
        const hasDeps = wf.depends_on_workflow_id != null;
        const isLast = idx === workflows.length - 1;

        return (
          <div key={wf.id} className="flex gap-4">
            <div className="flex flex-col items-center">
              <div className={`h-4 w-4 rounded-full ${statusDot[wf.status]} ring-2 ring-surface-primary`} />
              {!isLast && <div className="w-0.5 flex-1 bg-border" />}
            </div>

            <div className="flex flex-col gap-1 pb-6">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-content-primary">{wf.workflow_name}</span>
                <Badge color={statusColor[wf.status]} size="sm" variant="status">
                  {t(`multi_workflow.status_${wf.status}`)}
                </Badge>
                <Badge color="blue" size="sm">{t(`multi_workflow.mode_${wf.mode}`)}</Badge>
              </div>

              {hasDeps && (
                <p className="text-xs text-content-quaternary">
                  {t('multi_workflow.depends_on')}: {wf.depends_on_workflow_id}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
