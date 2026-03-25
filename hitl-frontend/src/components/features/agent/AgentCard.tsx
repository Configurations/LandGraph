import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import type { AgentInfo } from '../../../api/types';

interface AgentCardProps {
  agent: AgentInfo;
  teamId: string;
  className?: string;
}

const typeColorMap: Record<string, 'blue' | 'green' | 'orange' | 'purple'> = {
  orchestrator: 'purple',
  single: 'blue',
  lead: 'green',
};

export function AgentCard({
  agent,
  teamId,
  className = '',
}: AgentCardProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(`/teams/${teamId}/agents/${agent.id}/chat`);
  };

  const typeColor = typeColorMap[agent.type] ?? 'blue';

  return (
    <button
      onClick={handleClick}
      className={[
        'flex flex-col items-center gap-2 rounded-lg border border-border bg-surface-secondary p-4',
        'hover:bg-surface-hover transition-colors cursor-pointer text-center w-full',
        className,
      ].join(' ')}
    >
      <div className="relative">
        <Avatar name={agent.name} imageUrl={agent.avatar_url} size="md" />
        <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-accent-green border-2 border-surface-secondary" />
      </div>
      <div className="min-w-0 w-full">
        <p className="text-sm font-medium text-content-primary truncate">{agent.name}</p>
        <p className="text-xs text-content-tertiary truncate">{agent.id}</p>
      </div>
      <div className="flex items-center gap-2">
        <Badge size="sm" color={typeColor}>{t(`agent.type_${agent.type}`)}</Badge>
        {agent.pending_questions > 0 && (
          <Badge variant="count" color="red" size="sm">
            {agent.pending_questions}
          </Badge>
        )}
      </div>
    </button>
  );
}
