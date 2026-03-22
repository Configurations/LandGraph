import { useTranslation } from 'react-i18next';
import { Card } from '../../ui/Card';
import { Avatar } from '../../ui/Avatar';
import type { AgentInfo } from '../../../api/types';

interface ProjectTeamGridProps {
  agents: AgentInfo[];
  members: string[];
  onAgentClick?: (agentId: string) => void;
  className?: string;
}

export function ProjectTeamGrid({
  agents,
  members,
  onAgentClick,
  className = '',
}: ProjectTeamGridProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={`flex flex-col gap-6 ${className}`}>
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-widest text-content-quaternary mb-2">
          {t('project_detail.agents')}
        </h3>
        {agents.length === 0 ? (
          <p className="text-sm text-content-tertiary">{t('agent.no_agents')}</p>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
            {agents.map((agent) => (
              <Card
                key={agent.id}
                variant={onAgentClick ? 'interactive' : 'flat'}
                onClick={onAgentClick ? () => onAgentClick(agent.id) : undefined}
              >
                <div className="flex items-center gap-2">
                  <Avatar name={agent.name} size="sm" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-content-primary truncate">
                      {agent.name}
                    </p>
                    <p className="text-xs text-content-tertiary">{agent.type}</p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-widest text-content-quaternary mb-2">
          {t('project_detail.members')}
        </h3>
        {members.length === 0 ? (
          <p className="text-sm text-content-tertiary">{t('project_detail.no_members')}</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {members.map((name) => (
              <div key={name} className="flex items-center gap-2 rounded-lg bg-surface-tertiary px-3 py-2">
                <Avatar name={name} size="sm" />
                <span className="text-sm text-content-primary">{name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
