import { useTranslation } from 'react-i18next';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import type { PRResponse } from '../../../api/types';

interface PRRowProps {
  pr: PRResponse;
  onClick: () => void;
  className?: string;
}

const statusColor: Record<string, 'green' | 'blue' | 'orange' | 'red' | 'purple'> = {
  draft: 'purple',
  open: 'blue',
  approved: 'green',
  changes_requested: 'orange',
  merged: 'green',
  closed: 'red',
};

function formatRelativeTime(
  iso: string,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return t('time.just_now');
  if (minutes < 60) return t('time.minutes_ago', { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('time.hours_ago', { count: hours });
  const days = Math.floor(hours / 24);
  return t('time.days_ago', { count: days });
}

export function PRRow({ pr, onClick, className = '' }: PRRowProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <button
      onClick={onClick}
      className={[
        'w-full flex items-center gap-3 px-3 py-2 text-left rounded-lg',
        'hover:bg-surface-hover transition-colors cursor-pointer',
        className,
      ].join(' ')}
    >
      <Avatar name={pr.author} size="sm" />
      <span className="flex-1 truncate text-sm text-content-primary">{pr.title}</span>
      {pr.issue_id && (
        <span className="font-mono text-xs text-content-tertiary shrink-0">{pr.issue_id}</span>
      )}
      <span className="text-xs text-content-quaternary shrink-0">
        {t('pr.files_count', { count: pr.files_changed })}
      </span>
      <span className="text-xs text-accent-green shrink-0">+{pr.additions}</span>
      <span className="text-xs text-accent-red shrink-0">-{pr.deletions}</span>
      <Badge size="sm" color={statusColor[pr.status] ?? 'blue'}>
        {t(`pr.status_${pr.status}`)}
      </Badge>
      <span className="text-xs text-content-quaternary shrink-0">
        {formatRelativeTime(pr.updated_at, t)}
      </span>
    </button>
  );
}
