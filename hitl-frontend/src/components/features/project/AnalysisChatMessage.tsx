import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import type { AnalysisMessage } from '../../../api/types';

interface AnalysisChatMessageProps {
  message: AnalysisMessage;
  className?: string;
}

export function AnalysisChatMessage({ message, className = '' }: AnalysisChatMessageProps): JSX.Element {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const time = new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (message.type === 'system') {
    return (
      <p className={`text-center text-xs italic text-content-quaternary py-1 ${className}`}>
        {message.content}
      </p>
    );
  }

  const isUser = message.sender === 'user';
  const isQuestion = message.type === 'question';
  const isArtifact = message.type === 'artifact';
  const isResult = message.type === 'result';

  return (
    <div className={`flex max-w-[85%] gap-2 ${isUser ? 'self-end flex-row-reverse' : 'self-start'} ${className}`}>
      {!isUser && <Avatar name="Agent" size="sm" className="flex-shrink-0 mt-1" />}
      <div className="flex flex-col gap-1">
        <div
          className={[
            'rounded-lg px-3 py-2 text-sm',
            isUser ? 'bg-accent-blue/20 text-content-primary' : 'bg-surface-tertiary text-content-primary',
            isQuestion && message.status === 'pending' ? 'border border-accent-orange' : '',
          ].join(' ')}
        >
          {isQuestion && (
            <div className="flex items-center gap-1.5 mb-1">
              <Badge size="sm" color="orange">{t('analysis.question_badge')}</Badge>
              {message.status === 'pending' && (
                <span className="h-2 w-2 rounded-full bg-accent-orange animate-pulse" />
              )}
            </div>
          )}
          {isResult && (
            <Badge
              size="sm"
              color={message.content.includes('fail') ? 'red' : 'green'}
              className="mb-1"
            >
              {message.content.includes('fail') ? t('analysis.failed') : t('analysis.completed')}
            </Badge>
          )}
          {isArtifact ? (
            <div>
              <Badge size="sm" color="purple" className="mb-1">{t('analysis.artifact_badge')}</Badge>
              <div className={expanded ? '' : 'max-h-[300px] overflow-hidden'}>
                <MarkdownRenderer content={message.content} />
              </div>
              {message.content.length > 500 && (
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="text-xs text-accent-blue mt-1 hover:underline"
                >
                  {expanded ? '\u25B2' : '\u25BC'}
                </button>
              )}
            </div>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>
        <span className={`text-[10px] text-content-quaternary px-1 ${isUser ? 'text-right' : ''}`}>
          {time}
        </span>
      </div>
    </div>
  );
}
