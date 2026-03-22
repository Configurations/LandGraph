import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { OverviewData } from '../../../api/types';

interface OverviewCardsProps {
  data: OverviewData;
  className?: string;
}

interface CardConfig {
  labelKey: string;
  value: string | number;
  badge?: number;
  color: string;
  icon: JSX.Element;
}

export function OverviewCards({ data, className = '' }: OverviewCardsProps): JSX.Element {
  const { t } = useTranslation();

  const cards: CardConfig[] = [
    {
      labelKey: 'dashboard.pending_questions',
      value: data.pending_questions,
      badge: data.pending_questions,
      color: 'text-accent-orange',
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      labelKey: 'dashboard.active_tasks',
      value: data.active_tasks,
      color: 'text-accent-blue',
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
    {
      labelKey: 'dashboard.total_cost',
      value: `$${data.total_cost.toFixed(2)}`,
      color: 'text-accent-green',
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
  ];

  return (
    <div className={`grid grid-cols-1 sm:grid-cols-3 gap-4 ${className}`}>
      {cards.map((card) => (
        <div
          key={card.labelKey}
          className="rounded-lg border border-border bg-surface-secondary p-4 flex items-start gap-3"
        >
          <div className={`shrink-0 ${card.color}`}>{card.icon}</div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-content-tertiary">{t(card.labelKey)}</p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xl font-semibold text-content-primary">{card.value}</span>
              {card.badge !== undefined && card.badge > 0 && (
                <Badge variant="count" color="red" size="sm">{card.badge}</Badge>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
