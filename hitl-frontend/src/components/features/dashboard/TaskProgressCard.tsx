import { useTranslation } from 'react-i18next';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import type { ActiveTask } from '../../../api/types';

interface TaskProgressCardProps {
  task: ActiveTask;
  className?: string;
}

function formatElapsed(iso: string, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return t('time.just_now');
  if (minutes < 60) return t('time.minutes_ago', { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('time.hours_ago', { count: hours });
  const days = Math.floor(hours / 24);
  return t('time.days_ago', { count: days });
}

const statusColorMap: Record<string, 'blue' | 'green' | 'orange' | 'red'> = {
  running: 'blue',
  complete: 'green',
  pending: 'orange',
  error: 'red',
};

export function TaskProgressCard({
  task,
  className = '',
}: TaskProgressCardProps): JSX.Element {
  const { t } = useTranslation();
  const statusColor = statusColorMap[task.status] ?? 'blue';

  return (
    <div className={`flex items-center gap-3 rounded-lg border border-border bg-surface-secondary p-3 ${className}`}>
      <Avatar name={task.agent_id} size="sm" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-content-primary truncate">{task.agent_id}</span>
          <Badge size="sm" color="purple">{task.phase}</Badge>
          <Badge size="sm" color={statusColor} variant="status">{task.status}</Badge>
        </div>
        <p className="text-xs text-content-tertiary mt-0.5">
          {task.project_slug} - {formatElapsed(task.started_at, t)}
        </p>
      </div>
      <span className="text-xs font-mono text-content-secondary shrink-0">
        ${task.cost_usd.toFixed(4)}
      </span>
    </div>
  );
}
