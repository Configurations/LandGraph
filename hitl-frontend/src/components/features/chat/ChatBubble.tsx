import { Avatar } from '../../ui/Avatar';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import type { ChatMessage } from '../../../api/types';

interface ChatBubbleProps {
  message: ChatMessage;
  isUser: boolean;
  agentName?: string;
  agentAvatarUrl?: string | null;
  className?: string;
}

export function ChatBubble({
  message,
  isUser,
  agentName,
  agentAvatarUrl,
  className = '',
}: ChatBubbleProps): JSX.Element {
  const time = new Date(message.created_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div
      className={[
        'flex max-w-[80%] gap-2',
        isUser ? 'self-end flex-row-reverse' : 'self-start',
        className,
      ].join(' ')}
    >
      {!isUser && (
        <Avatar
          name={agentName || message.agent_id}
          imageUrl={agentAvatarUrl}
          size="sm"
          className="flex-shrink-0 mt-1"
        />
      )}
      <div className="flex flex-col gap-1">
        <div
          className={[
            'rounded-lg px-3 py-2 text-sm',
            isUser
              ? 'bg-accent-blue/20 text-content-primary'
              : 'bg-surface-tertiary text-content-primary',
          ].join(' ')}
        >
          <MarkdownRenderer content={message.content} />
        </div>
        <span className={[
          'text-[10px] text-content-quaternary px-1',
          isUser ? 'text-right' : '',
        ].join(' ')}>{time}</span>
      </div>
    </div>
  );
}
