import { useTranslation } from 'react-i18next';
import { PriorityBadge } from './PriorityBadge';
import { IssueStatusIcon } from './IssueStatusIcon';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import type { IssueResponse } from '../../../api/types';

interface IssueRowProps {
  issue: IssueResponse;
  onClick: () => void;
  className?: string;
}

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

const MAX_VISIBLE_TAGS = 2;

export function IssueRow({
  issue,
  onClick,
  className = '',
}: IssueRowProps): JSX.Element {
  const { t } = useTranslation();
  const tags = issue.tags ?? [];
  const visibleTags = tags.slice(0, MAX_VISIBLE_TAGS);
  const extraTagCount = tags.length - MAX_VISIBLE_TAGS;

  return (
    <button
      onClick={onClick}
      className={[
        'w-full flex items-center gap-3 px-3 py-2 text-left rounded-lg',
        'hover:bg-surface-hover transition-colors cursor-pointer',
        className,
      ].join(' ')}
    >
      <PriorityBadge priority={issue.priority} />
      <span className="font-mono text-xs text-content-tertiary shrink-0">
        {issue.id}
      </span>
      <IssueStatusIcon status={issue.status} size={14} />
      {issue.is_blocked && (
        <svg className="h-3.5 w-3.5 text-accent-red shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m0 0v2m0-2h2m-2 0H10m4-6V4a2 2 0 00-2-2h0a2 2 0 00-2 2v7" />
        </svg>
      )}
      {issue.blocking_count > 0 && (
        <span className="text-[10px] font-medium text-accent-orange shrink-0">
          {t('issue.blocking_count', { count: issue.blocking_count })}
        </span>
      )}
      <span className="flex-1 truncate text-sm text-content-primary">
        {issue.title}
      </span>
      {visibleTags.map((tag) => (
        <Badge key={tag} size="sm" color="purple">{tag}</Badge>
      ))}
      {extraTagCount > 0 && (
        <span className="text-[10px] text-content-quaternary">+{extraTagCount}</span>
      )}
      {issue.assignee && <Avatar name={issue.assignee} size="sm" />}
      <span className="text-xs text-content-quaternary shrink-0">
        {formatRelativeTime(issue.updated_at, t)}
      </span>
    </button>
  );
}
