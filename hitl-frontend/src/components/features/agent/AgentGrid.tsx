import { useTranslation } from 'react-i18next';
import { AgentCard } from './AgentCard';
import type { AgentInfo } from '../../../api/types';

interface AgentGridProps {
  agents: AgentInfo[];
  teamId: string;
  className?: string;
}

export function AgentGrid({
  agents,
  teamId,
  className = '',
}: AgentGridProps): JSX.Element {
  const { t } = useTranslation();

  if (agents.length === 0) {
    return (
      <div className={`text-center py-12 text-content-tertiary text-sm ${className}`}>
        {t('agent.no_agents')}
      </div>
    );
  }

  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 ${className}`}>
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} teamId={teamId} />
      ))}
    </div>
  );
}
