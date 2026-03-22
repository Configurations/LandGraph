import { useTranslation } from 'react-i18next';
import type { AutomationStats as AutomationStatsType } from '../../../api/types';

interface AutomationStatsProps {
  stats: AutomationStatsType;
  className?: string;
}

interface Segment {
  labelKey: string;
  value: number;
  color: string;
}

export function AutomationStats({
  stats,
  className = '',
}: AutomationStatsProps): JSX.Element {
  const { t } = useTranslation();

  const total = stats.total_decisions || 1;
  const segments: Segment[] = [
    { labelKey: 'automation.auto_approved', value: stats.auto_approved, color: 'bg-accent-green' },
    { labelKey: 'automation.manual_reviewed', value: stats.manual_reviewed, color: 'bg-accent-blue' },
    { labelKey: 'automation.rejected', value: stats.rejected, color: 'bg-accent-red' },
  ];

  return (
    <div className={`rounded-xl border border-border bg-surface-secondary p-4 ${className}`}>
      <h4 className="text-sm font-semibold text-content-secondary mb-3">
        {t('automation.stats_title')}
      </h4>

      <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-tertiary">
        {segments.map((seg) => {
          const pct = (seg.value / total) * 100;
          if (pct === 0) return null;
          return (
            <div
              key={seg.labelKey}
              className={`${seg.color} transition-all`}
              style={{ width: `${pct}%` }}
            />
          );
        })}
      </div>

      <div className="flex gap-4 mt-3">
        {segments.map((seg) => {
          const pct = Math.round((seg.value / total) * 100);
          return (
            <div key={seg.labelKey} className="flex items-center gap-1.5">
              <span className={`inline-block h-2 w-2 rounded-full ${seg.color}`} />
              <span className="text-xs text-content-tertiary">
                {t(seg.labelKey)} ({pct}%)
              </span>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-content-quaternary mt-2">
        {t('automation.total_decisions', { count: stats.total_decisions })}
      </p>
    </div>
  );
}
