import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import { Avatar } from '../../ui/Avatar';
import { ValidationBadge } from './ValidationBadge';
import type { DeliverableResponse } from '../../../api/types';

interface DeliverableCardProps {
  deliverable: DeliverableResponse;
  onClick: () => void;
  className?: string;
}

const typeBadgeColor: Record<string, 'blue' | 'green' | 'orange' | 'purple' | 'yellow' | 'red'> = {
  DOC: 'blue',
  CODE: 'green',
  SPECS: 'purple',
  TEST: 'orange',
  CONFIG: 'yellow',
  DESIGN: 'red',
};

function formatRelativeTime(iso: string, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return t('time.just_now');
  if (minutes < 60) return t('time.minutes_ago', { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('time.hours_ago', { count: hours });
  const days = Math.floor(hours / 24);
  return t('time.days_ago', { count: days });
}

export function DeliverableCard({
  deliverable,
  onClick,
  className = '',
}: DeliverableCardProps): JSX.Element {
  const { t } = useTranslation();
  const typeColor = typeBadgeColor[deliverable.deliverable_type.toUpperCase()] ?? 'blue';

  return (
    <button
      onClick={onClick}
      className={[
        'w-full text-left rounded-lg border border-border bg-surface-secondary p-3',
        'hover:bg-surface-hover transition-colors cursor-pointer',
        className,
      ].join(' ')}
    >
      <div className="flex items-start gap-3">
        <Avatar name={deliverable.agent_id} size="sm" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-content-primary truncate">
              {deliverable.key}
            </span>
            <Badge size="sm" color={typeColor}>
              {deliverable.deliverable_type}
            </Badge>
          </div>
          <div className="flex items-center gap-2 text-xs text-content-tertiary">
            <span>{deliverable.category}</span>
            <span>-</span>
            <span>{formatRelativeTime(deliverable.created_at, t)}</span>
          </div>
        </div>
        <ValidationBadge status={deliverable.status} />
      </div>
    </button>
  );
}
