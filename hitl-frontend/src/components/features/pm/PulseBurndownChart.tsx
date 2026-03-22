import { useTranslation } from 'react-i18next';
import { Card } from '../../ui/Card';
import type { BurndownPoint } from '../../../api/types';

interface PulseBurndownChartProps {
  points: BurndownPoint[];
  className?: string;
}

export function PulseBurndownChart({
  points,
  className = '',
}: PulseBurndownChartProps): JSX.Element {
  const { t } = useTranslation();

  const maxValue = points.reduce(
    (max, p) => Math.max(max, p.remaining + p.completed),
    1,
  );

  const displayPoints = points.slice(-14);

  return (
    <Card className={className}>
      <h3 className="text-sm font-semibold mb-3">{t('pulse.burndown_chart')}</h3>
      {displayPoints.length === 0 ? (
        <p className="text-xs text-content-tertiary">{t('pulse.no_data')}</p>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex items-end gap-1 h-32">
            {displayPoints.map((point) => {
              const completedPct = (point.completed / maxValue) * 100;
              const remainingPct = (point.remaining / maxValue) * 100;
              return (
                <div
                  key={point.date}
                  className="flex-1 flex flex-col justify-end h-full"
                  title={`${point.date}: ${point.completed} / ${point.remaining + point.completed}`}
                >
                  <div
                    className="bg-content-quaternary/40 rounded-t-sm transition-all"
                    style={{ height: `${remainingPct}%` }}
                  />
                  <div
                    className="bg-accent-green rounded-b-sm transition-all"
                    style={{ height: `${completedPct}%` }}
                  />
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-4 justify-center">
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm bg-accent-green" />
              <span className="text-xs text-content-tertiary">{t('pulse.completed')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm bg-content-quaternary/40" />
              <span className="text-xs text-content-tertiary">{t('pulse.remaining')}</span>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
