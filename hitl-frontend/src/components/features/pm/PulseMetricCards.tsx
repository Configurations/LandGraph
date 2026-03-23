import { useTranslation } from 'react-i18next';
import { Card } from '../../ui/Card';
import type { MetricValue } from '../../../api/types';

interface PulseMetricCardsProps {
  velocity: MetricValue;
  throughput: MetricValue;
  cycleTime: MetricValue;
  className?: string;
}

function MetricCard({ metric, labelKey }: { metric: MetricValue; labelKey: string }): JSX.Element {
  const { t } = useTranslation();

  return (
    <Card>
      <p className="text-xs text-content-tertiary mb-1">{t(labelKey)}</p>
      <span className="text-2xl font-bold text-content-primary">{metric?.value ?? '—'}</span>
      <p className="text-xs text-content-quaternary mt-1">{metric?.sub ?? ''}</p>
    </Card>
  );
}

export function PulseMetricCards({
  velocity,
  throughput,
  cycleTime,
  className = '',
}: PulseMetricCardsProps): JSX.Element {
  return (
    <div className={`grid grid-cols-2 lg:grid-cols-3 gap-3 ${className}`}>
      <MetricCard metric={velocity} labelKey="pulse.velocity" />
      <MetricCard metric={throughput} labelKey="pulse.throughput" />
      <MetricCard metric={cycleTime} labelKey="pulse.cycle_time" />
    </div>
  );
}
