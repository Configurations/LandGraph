import { useTranslation } from 'react-i18next';
import type { IssueStatus } from '../../../api/types';

interface PulseStatusBarProps {
  breakdown: Record<IssueStatus, number>;
  className?: string;
}

const statusColors: Record<IssueStatus, string> = {
  backlog: 'bg-content-quaternary',
  todo: 'bg-accent-blue',
  'in-progress': 'bg-accent-orange',
  'in-review': 'bg-accent-purple',
  done: 'bg-accent-green',
};

const STATUS_ORDER: IssueStatus[] = ['backlog', 'todo', 'in-progress', 'in-review', 'done'];

export function PulseStatusBar({ breakdown, className = '' }: PulseStatusBarProps): JSX.Element {
  const { t } = useTranslation();
  const total = STATUS_ORDER.reduce((sum, s) => sum + (breakdown[s] ?? 0), 0);

  if (total === 0) {
    return (
      <div className={`h-6 rounded-full bg-surface-tertiary ${className}`} />
    );
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex h-6 rounded-full overflow-hidden">
        {STATUS_ORDER.map((status) => {
          const count = breakdown[status] ?? 0;
          if (count === 0) return null;
          const pct = (count / total) * 100;
          return (
            <div
              key={status}
              className={`${statusColors[status]} transition-all`}
              style={{ width: `${pct}%` }}
              title={`${t(`issue.status_${status}`)}: ${count}`}
            />
          );
        })}
      </div>
      <div className="flex gap-3 flex-wrap">
        {STATUS_ORDER.map((status) => {
          const count = breakdown[status] ?? 0;
          if (count === 0) return null;
          return (
            <div key={status} className="flex items-center gap-1.5">
              <span className={`inline-block h-2.5 w-2.5 rounded-sm ${statusColors[status]}`} />
              <span className="text-xs text-content-tertiary">
                {t(`issue.status_${status}`)} ({count})
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
