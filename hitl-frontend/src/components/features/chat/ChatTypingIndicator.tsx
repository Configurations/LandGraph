import { useTranslation } from 'react-i18next';

interface ChatTypingIndicatorProps {
  agentName: string;
  className?: string;
}

export function ChatTypingIndicator({
  agentName,
  className = '',
}: ChatTypingIndicatorProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={`flex items-center gap-2 px-4 py-2 ${className}`}>
      <div className="flex gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-content-quaternary animate-bounce [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 rounded-full bg-content-quaternary animate-bounce [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 rounded-full bg-content-quaternary animate-bounce [animation-delay:300ms]" />
      </div>
      <span className="text-xs text-content-tertiary">
        {t('chat.typing', { agent: agentName })}
      </span>
    </div>
  );
}
