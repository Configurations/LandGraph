import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AgentChat } from '../components/features/chat/AgentChat';

export function AgentChatPage(): JSX.Element {
  const { t } = useTranslation();
  const { teamId = '', agentId = '' } = useParams<{ teamId: string; agentId: string }>();

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-4 py-3">
        <h2 className="text-base font-semibold">
          {t('chat.chat_with', { agent: agentId })}
        </h2>
      </div>
      <AgentChat teamId={teamId} agentId={agentId} className="flex-1 min-h-0" />
    </div>
  );
}
