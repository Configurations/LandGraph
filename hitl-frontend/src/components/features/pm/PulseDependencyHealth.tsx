import { useTranslation } from 'react-i18next';
import { Card } from '../../ui/Card';
import type { DependencyHealth } from '../../../api/types';

interface PulseDependencyHealthProps {
  health: DependencyHealth;
  className?: string;
}

interface StatCardProps {
  labelKey: string;
  value: number;
  color: string;
}

function StatCard({ labelKey, value, color }: StatCardProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center rounded-lg border border-border bg-surface-tertiary p-3">
      <span className={`text-2xl font-bold ${color}`}>{value}</span>
      <span className="text-xs text-content-tertiary mt-1">{t(labelKey)}</span>
    </div>
  );
}

export function PulseDependencyHealth({
  health,
  className = '',
}: PulseDependencyHealthProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <Card className={className}>
      <h3 className="text-sm font-semibold mb-3">{t('pulse.dependency_health')}</h3>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <StatCard labelKey="pulse.blocked" value={health.blocked} color="text-accent-red" />
        <StatCard labelKey="pulse.blocking" value={health.blocking} color="text-accent-orange" />
        <StatCard labelKey="pulse.chains" value={health.chains} color="text-accent-purple" />
      </div>
      {(health.bottlenecks?.length ?? 0) > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-xs font-medium text-content-secondary mb-1">
            {t('pulse.bottlenecks')}
          </p>
          {health.bottlenecks.map((issue) => (
            <div
              key={issue.id}
              className="flex items-center gap-2 rounded-md bg-surface-tertiary px-2 py-1"
            >
              <span className="font-mono text-xs text-content-tertiary">{issue.id}</span>
              <span className="text-xs text-content-primary truncate">{issue.title}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
