import { useTranslation } from 'react-i18next';
import { Card } from '../../ui/Card';
import type { MetricValue } from '../../../api/types';

interface PulseMetricCardsProps {
  velocity: MetricValue;
  throughput: MetricValue;
  cycleTime: MetricValue;
  burndownTotal: MetricValue;
  className?: string;
}

interface MetricCardProps {
  metric: MetricValue;
  labelKey: string;
}

function MetricCard({ metric, labelKey }: MetricCardProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <Card>
      <p className="text-xs text-content-tertiary mb-1">{t(labelKey)}</p>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold text-content-primary">{metric.value}</span>
        <span className="text-xs text-content-quaternary">{metric.unit}</span>
      </div>
      <p className="text-xs text-content-tertiary mt-1">{metric.label}</p>
    </Card>
  );
}

export function PulseMetricCards({
  velocity,
  throughput,
  cycleTime,
  burndownTotal,
  className = '',
}: PulseMetricCardsProps): JSX.Element {
  return (
    <div className={`grid grid-cols-2 lg:grid-cols-4 gap-3 ${className}`}>
      <MetricCard metric={velocity} labelKey="pulse.velocity" />
      <MetricCard metric={throughput} labelKey="pulse.throughput" />
      <MetricCard metric={cycleTime} labelKey="pulse.cycle_time" />
      <MetricCard metric={burndownTotal} labelKey="pulse.burndown" />
    </div>
  );
}
