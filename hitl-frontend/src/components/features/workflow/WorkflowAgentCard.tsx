import { useTranslation } from 'react-i18next';
import { Card } from '../../ui/Card';
import type { AgentRunStatus, PhaseAgent } from '../../../api/types';

interface WorkflowAgentCardProps {
  agent: PhaseAgent;
  onClick?: () => void;
  className?: string;
}

const statusDotColor: Record<AgentRunStatus, string> = {
  idle: 'bg-content-quaternary',
  running: 'bg-accent-orange animate-pulse',
  completed: 'bg-accent-green',
  error: 'bg-accent-red',
};

export function WorkflowAgentCard({
  agent,
  onClick,
  className = '',
}: WorkflowAgentCardProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <Card
      variant={onClick ? 'interactive' : 'flat'}
      onClick={onClick}
      className={className}
    >
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${statusDotColor[agent.status]}`}
          aria-label={t(`workflow.agent_status_${agent.status}`)}
        />
        <span className="text-sm font-medium text-content-primary">{agent.name}</span>
      </div>
      <p className="text-xs text-content-tertiary mt-1">
        {t(`workflow.agent_status_${agent.status}`)}
      </p>
      {agent.task_id && (
        <p className="text-xs font-mono text-accent-blue mt-1 truncate">{agent.task_id}</p>
      )}
    </Card>
  );
}
