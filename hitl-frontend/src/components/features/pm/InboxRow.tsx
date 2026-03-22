import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Avatar } from '../../ui/Avatar';
import type { PMNotification } from '../../../api/types';

interface InboxRowProps {
  notification: PMNotification;
  onMarkRead: () => void;
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

export function InboxRow({
  notification,
  onMarkRead,
  className = '',
}: InboxRowProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div
      onClick={!notification.read ? onMarkRead : undefined}
      className={[
        'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors',
        notification.read ? 'opacity-60' : 'cursor-pointer hover:bg-surface-hover',
        className,
      ].join(' ')}
    >
      {!notification.read && (
        <span className="h-2 w-2 shrink-0 rounded-full bg-accent-blue" />
      )}
      {notification.read && <span className="h-2 w-2 shrink-0" />}
      <Avatar name={notification.avatar} size="sm" />
      <span className="flex-1 text-sm text-content-primary truncate">
        {notification.text}
      </span>
      {notification.issue_id && (
        <Link
          to={`/issues?selected=${notification.issue_id}`}
          className="font-mono text-xs text-accent-blue hover:underline shrink-0"
          onClick={(e) => e.stopPropagation()}
        >
          {notification.issue_id}
        </Link>
      )}
      <span className="text-xs text-content-quaternary shrink-0">
        {formatRelativeTime(notification.created_at, t)}
      </span>
    </div>
  );
}
