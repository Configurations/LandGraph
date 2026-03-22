import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { AgentGrid } from '../components/features/agent/AgentGrid';
import { Spinner } from '../components/ui/Spinner';
import * as agentsApi from '../api/agents';
import type { AgentInfo } from '../api/types';

export function AgentsPage(): JSX.Element {
  const { t } = useTranslation();
  const { teamId = '' } = useParams<{ teamId: string }>();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!teamId) return;
    setLoading(true);
    agentsApi
      .listAgents(teamId)
      .then(setAgents)
      .catch(() => setAgents([]))
      .finally(() => setLoading(false));
  }, [teamId]);

  return (
    <PageContainer>
      <h2 className="text-xl font-semibold mb-6">{t('agent.agents')}</h2>
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Spinner />
        </div>
      ) : (
        <AgentGrid agents={agents} teamId={teamId} />
      )}
    </PageContainer>
  );
}
