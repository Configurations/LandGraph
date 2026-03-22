import { useTranslation } from 'react-i18next';
import { TaskProgressCard } from './TaskProgressCard';
import type { ActiveTask } from '../../../api/types';

interface ActiveTasksListProps {
  tasks: ActiveTask[];
  className?: string;
}

export function ActiveTasksList({
  tasks,
  className = '',
}: ActiveTasksListProps): JSX.Element {
  const { t } = useTranslation();

  if (tasks.length === 0) {
    return (
      <div className={`text-center py-8 text-content-tertiary text-sm ${className}`}>
        {t('dashboard.no_active_tasks')}
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <h3 className="text-sm font-semibold text-content-secondary">
        {t('dashboard.active_tasks')} ({tasks.length})
      </h3>
      {tasks.map((task) => (
        <TaskProgressCard key={task.task_id} task={task} />
      ))}
    </div>
  );
}
