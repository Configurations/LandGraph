import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import type { ChatMessage } from '../../../api/types';

interface ChatBubbleProps {
  message: ChatMessage;
  isUser: boolean;
  className?: string;
}

export function ChatBubble({
  message,
  isUser,
  className = '',
}: ChatBubbleProps): JSX.Element {
  const time = new Date(message.created_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div
      className={[
        'flex flex-col max-w-[80%] gap-1',
        isUser ? 'self-end items-end' : 'self-start items-start',
        className,
      ].join(' ')}
    >
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
      <span className="text-[10px] text-content-quaternary px-1">{time}</span>
    </div>
  );
}
