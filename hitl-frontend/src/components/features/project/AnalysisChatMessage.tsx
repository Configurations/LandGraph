import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import { InteractiveQuestions } from '../hitl/InteractiveQuestions';
import { parseQuestions, stripQuestionMarkers } from '../../../utils/questionParser';
import type { AnalysisMessage } from '../../../api/types';

interface AnalysisChatMessageProps {
  message: AnalysisMessage;
  onReply?: (requestId: string, response: string) => void;
  className?: string;
}

export function AnalysisChatMessage({ message, onReply, className = '' }: AnalysisChatMessageProps): JSX.Element {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [sent, setSent] = useState(false);
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
  const isPending = isQuestion && message.status === 'pending';

  const parsed = isQuestion && isPending && !sent ? parseQuestions(message.content) : null;

  const agentName = message.agent_id || 'Agent';
  const avatarUrl = message.agent_avatar || undefined;

  return (
    <div className={`flex max-w-[85%] gap-2 ${isUser ? 'self-end flex-row-reverse' : 'self-start'} ${className}`}>
      {!isUser && (
        avatarUrl
          ? <img src={avatarUrl} alt={agentName} className="w-16 h-16 rounded-full flex-shrink-0 mt-1 object-cover" />
          : <Avatar name={agentName} size="md" className="flex-shrink-0 mt-1" />
      )}
      <div className="flex flex-col gap-1 flex-1">
        {!isUser && message.agent_id && (
          <span className="text-[10px] font-semibold text-accent-blue px-1">{agentName}</span>
        )}

        {parsed && !sent ? (
          <InteractiveQuestions
            parsed={parsed}
            onSubmit={(response) => {
              if (onReply && message.request_id) {
                onReply(message.request_id, response);
                setSent(true);
              }
            }}
          />
        ) : (
          <div
            className={[
              'rounded-lg px-3 py-2 text-sm',
              isUser ? 'bg-accent-blue/20 text-content-primary' : 'bg-surface-tertiary text-content-primary',
              isPending && !parsed ? 'border border-accent-orange' : '',
              sent ? 'border border-green-500/30' : '',
            ].join(' ')}
          >
            {isQuestion && !sent && (
              <div className="flex items-center gap-1.5 mb-1">
                <Badge size="sm" color="orange">{t('analysis.question_badge')}</Badge>
                {isPending && <span className="h-2 w-2 rounded-full bg-accent-orange animate-pulse" />}
              </div>
            )}
            {sent && (
              <div className="flex items-center gap-1.5 mb-1">
                <Badge size="sm" color="green">Repondu</Badge>
              </div>
            )}
            {isResult && (
              <Badge size="sm" color={message.content.includes('fail') ? 'red' : 'green'} className="mb-1">
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
              <MarkdownRenderer content={stripQuestionMarkers(message.content)} />
            )}
          </div>
        )}

        <span className={`text-[10px] text-content-quaternary px-1 ${isUser ? 'text-right' : ''}`}>
          {time}
        </span>
      </div>
    </div>
  );
}
