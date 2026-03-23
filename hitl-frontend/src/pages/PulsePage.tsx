import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { Spinner } from '../components/ui/Spinner';
import { PulseStatusBar } from '../components/features/pm/PulseStatusBar';
import { PulseMetricCards } from '../components/features/pm/PulseMetricCards';
import { PulseTeamActivity } from '../components/features/pm/PulseTeamActivity';
import { PulseDependencyHealth } from '../components/features/pm/PulseDependencyHealth';
import { PulseBurndownChart } from '../components/features/pm/PulseBurndownChart';
import { useTeamStore } from '../stores/teamStore';
import * as pulseApi from '../api/pulse';
import type { PulseResponse } from '../api/types';

export function PulsePage(): JSX.Element {
  const { t } = useTranslation();
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const [data, setData] = useState<PulseResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    pulseApi
      .getPulse(activeTeamId ?? undefined)
      .then(setData)
      .finally(() => setLoading(false));
  }, [activeTeamId]);

  if (loading) {
    return (
      <PageContainer className="flex justify-center py-12">
        <Spinner />
      </PageContainer>
    );
  }

  if (!data) {
    return (
      <PageContainer>
        <p className="text-sm text-content-tertiary">{t('pulse.no_data')}</p>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <h2 className="text-xl font-semibold mb-6">{t('pulse.title')}</h2>
      <div className="flex flex-col gap-6">
        <PulseStatusBar distribution={data.status_distribution ?? {}} />
        <PulseMetricCards
          velocity={data.velocity}
          throughput={data.throughput}
          cycleTime={data.cycle_time}
        />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <PulseTeamActivity members={data.team_activity} />
          <PulseDependencyHealth health={data.dependency_health} />
        </div>
        <PulseBurndownChart points={data.burndown} />
      </div>
    </PageContainer>
  );
}
