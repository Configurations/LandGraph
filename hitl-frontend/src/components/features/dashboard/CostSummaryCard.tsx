import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { CostSummary } from '../../../api/types';

interface CostSummaryCardProps {
  costs: CostSummary[];
  budget: number;
  className?: string;
}

export function CostSummaryCard({
  costs,
  budget,
  className = '',
}: CostSummaryCardProps): JSX.Element {
  const { t } = useTranslation();

  const totalCost = useMemo(
    () => costs.reduce((sum, c) => sum + c.total_cost_usd, 0),
    [costs],
  );

  const byPhase = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of costs) {
      map.set(c.phase, (map.get(c.phase) ?? 0) + c.total_cost_usd);
    }
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  }, [costs]);

  const overBudget = budget > 0 && totalCost > budget;
  const percentage = budget > 0 ? Math.min((totalCost / budget) * 100, 100) : 0;

  return (
    <div className={`rounded-lg border border-border bg-surface-secondary p-4 ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-content-secondary">
          {t('dashboard.cost_summary')}
        </h3>
        {overBudget && (
          <Badge size="sm" color="red">{t('dashboard.over_budget')}</Badge>
        )}
      </div>

      <div className="flex items-baseline gap-2 mb-4">
        <span className="text-2xl font-bold text-content-primary">
          ${totalCost.toFixed(2)}
        </span>
        {budget > 0 && (
          <span className="text-sm text-content-tertiary">
            / ${budget.toFixed(2)}
          </span>
        )}
      </div>

      {budget > 0 && (
        <div className="h-2 rounded-full bg-surface-tertiary mb-4 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${overBudget ? 'bg-accent-red' : 'bg-accent-green'}`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      )}

      {byPhase.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-content-quaternary">
            {t('dashboard.cost_by_phase')}
          </h4>
          {byPhase.map(([phase, cost]) => {
            const phasePercentage = totalCost > 0 ? (cost / totalCost) * 100 : 0;
            return (
              <div key={phase} className="flex items-center gap-2">
                <span className="text-xs text-content-tertiary w-24 truncate">{phase}</span>
                <div className="flex-1 h-1.5 rounded-full bg-surface-tertiary overflow-hidden">
                  <div
                    className="h-full rounded-full bg-accent-blue"
                    style={{ width: `${phasePercentage}%` }}
                  />
                </div>
                <span className="text-xs font-mono text-content-secondary w-16 text-right">
                  ${cost.toFixed(2)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
