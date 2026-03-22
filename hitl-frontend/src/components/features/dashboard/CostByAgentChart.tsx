import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { CostSummary } from '../../../api/types';

interface CostByAgentChartProps {
  costs: CostSummary[];
  className?: string;
}

const agentColors: Record<string, string> = {
  orchestrator: 'bg-accent-purple',
  lead_dev: 'bg-accent-blue',
  dev_frontend: 'bg-accent-green',
  dev_backend: 'bg-accent-orange',
  dev_mobile: 'bg-accent-yellow',
  qa_engineer: 'bg-accent-red',
  architect: 'bg-accent-blue',
  ux_designer: 'bg-accent-purple',
  requirements_analyst: 'bg-accent-orange',
};

export function CostByAgentChart({
  costs,
  className = '',
}: CostByAgentChartProps): JSX.Element {
  const { t } = useTranslation();

  const byAgent = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of costs) {
      map.set(c.agent_id, (map.get(c.agent_id) ?? 0) + c.total_cost_usd);
    }
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  }, [costs]);

  const maxCost = useMemo(
    () => byAgent.reduce((max, [, cost]) => Math.max(max, cost), 0),
    [byAgent],
  );

  if (byAgent.length === 0) {
    return (
      <div className={`text-center py-6 text-content-tertiary text-sm ${className}`}>
        {t('dashboard.no_cost_data')}
      </div>
    );
  }

  return (
    <div className={`rounded-lg border border-border bg-surface-secondary p-4 ${className}`}>
      <h3 className="text-sm font-semibold text-content-secondary mb-3">
        {t('dashboard.cost_by_agent')}
      </h3>
      <div className="flex flex-col gap-2">
        {byAgent.map(([agentId, cost]) => {
          const widthPercent = maxCost > 0 ? (cost / maxCost) * 100 : 0;
          const barColor = agentColors[agentId] ?? 'bg-accent-blue';
          return (
            <div key={agentId} className="flex items-center gap-2">
              <span className="text-xs text-content-tertiary w-28 truncate">{agentId}</span>
              <div className="flex-1 h-3 rounded bg-surface-tertiary overflow-hidden">
                <div
                  className={`h-full rounded ${barColor}`}
                  style={{ width: `${widthPercent}%` }}
                />
              </div>
              <span className="text-xs font-mono text-content-secondary w-16 text-right">
                ${cost.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
