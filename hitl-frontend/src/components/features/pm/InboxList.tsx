import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InboxRow } from './InboxRow';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import type { PMNotification, PMNotificationType } from '../../../api/types';

interface InboxListProps {
  notifications: PMNotification[];
  onMarkRead: (id: string) => void;
  onMarkAllRead: () => void;
  className?: string;
}

type FilterTab = 'all' | PMNotificationType;

const FILTER_TABS: FilterTab[] = ['all', 'assigned', 'status_changed', 'blocked'];

export function InboxList({
  notifications,
  onMarkRead,
  onMarkAllRead,
  className = '',
}: InboxListProps): JSX.Element {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<FilterTab>('all');

  const items = notifications ?? [];
  const filtered =
    activeTab === 'all'
      ? items
      : items.filter((n) => n.type === activeTab);

  const unreadCount = items.filter((n) => !n.read).length;

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      <div className="flex items-center gap-2 overflow-x-auto">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={[
              'px-3 py-1 text-xs font-medium rounded-full transition-colors shrink-0',
              activeTab === tab
                ? 'bg-accent-blue/15 text-accent-blue'
                : 'text-content-tertiary hover:text-content-primary hover:bg-surface-hover',
            ].join(' ')}
          >
            {t(`inbox.tab_${tab}`)}
          </button>
        ))}
        <div className="flex-1" />
        {unreadCount > 0 && (
          <Button variant="ghost" size="sm" onClick={onMarkAllRead}>
            {t('inbox.mark_all_read')}
          </Button>
        )}
      </div>

      {filtered.length === 0 ? (
        <EmptyState titleKey="inbox.no_notifications" />
      ) : (
        <div className="flex flex-col">
          {filtered.map((n) => (
            <InboxRow
              key={n.id}
              notification={n}
              onMarkRead={() => onMarkRead(n.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
