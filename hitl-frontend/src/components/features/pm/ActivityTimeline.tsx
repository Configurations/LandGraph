import { useTranslation } from 'react-i18next';
import { ActivityEntryRow } from './ActivityEntryRow';
import { EmptyState } from '../../ui/EmptyState';
import type { ActivityEntry } from '../../../api/types';

interface ActivityTimelineProps {
  entries: ActivityEntry[];
  className?: string;
}

function groupByDate(entries: ActivityEntry[]): Map<string, ActivityEntry[]> {
  const groups = new Map<string, ActivityEntry[]>();
  for (const entry of entries) {
    const dateKey = new Date(entry.created_at).toLocaleDateString();
    const list = groups.get(dateKey) ?? [];
    list.push(entry);
    groups.set(dateKey, list);
  }
  return groups;
}

export function ActivityTimeline({
  entries,
  className = '',
}: ActivityTimelineProps): JSX.Element {
  const { t } = useTranslation();

  if (entries.length === 0) {
    return <EmptyState titleKey="activity.no_activity" className={className} />;
  }

  const grouped = groupByDate(entries);

  return (
    <div className={`flex flex-col ${className}`}>
      <h4 className="text-sm font-semibold text-content-secondary mb-3">
        {t('activity.title')}
      </h4>
      {Array.from(grouped.entries()).map(([date, dateEntries]) => (
        <div key={date}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-content-tertiary">{date}</span>
            <div className="flex-1 h-px bg-border" />
          </div>
          {dateEntries.map((entry) => (
            <ActivityEntryRow key={entry.id} entry={entry} />
          ))}
        </div>
      ))}
    </div>
  );
}
