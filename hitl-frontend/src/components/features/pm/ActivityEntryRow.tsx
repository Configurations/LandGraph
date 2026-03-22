import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { ActivityEntry } from '../../../api/types';

interface ActivityEntryRowProps {
  entry: ActivityEntry;
  className?: string;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

export function ActivityEntryRow({
  entry,
  className = '',
}: ActivityEntryRowProps): JSX.Element {
  const { t } = useTranslation();
  const sourceBadgeColor = entry.source === 'agent' ? 'blue' : 'purple';

  return (
    <div className={`flex items-start gap-3 ${className}`}>
      <div className="flex flex-col items-center pt-0.5">
        <div className="h-2 w-2 rounded-full bg-border" />
        <div className="w-px flex-1 bg-border" />
      </div>
      <div className="flex-1 pb-4">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-[10px] text-content-quaternary">
            {formatDate(entry.created_at)} {formatTime(entry.created_at)}
          </span>
          <Badge size="sm" color={sourceBadgeColor}>
            {t(`activity.source_${entry.source}`)}
          </Badge>
        </div>
        <p className="text-sm text-content-primary">
          <span className="font-medium">{entry.user_name}</span>
          {' '}
          <span className="text-content-secondary">
            {t(`activity.action_${entry.action}`, { defaultValue: entry.action })}
          </span>
          {entry.issue_id && (
            <span className="font-mono text-xs text-accent-blue ml-1">
              {entry.issue_id}
            </span>
          )}
        </p>
        {entry.detail && (
          <p className="text-xs text-content-tertiary mt-0.5">{entry.detail}</p>
        )}
      </div>
    </div>
  );
}
