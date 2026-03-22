import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Spinner } from '../../ui/Spinner';
import * as ragApi from '../../../api/rag';
import type { ConversationMessage } from '../../../api/types';

interface AnalysisChatProps {
  slug: string;
  taskId: string | null;
  className?: string;
}

export function AnalysisChat({ slug, taskId, className = '' }: AnalysisChatProps): JSX.Element {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [status, setStatus] = useState<'starting' | 'running' | 'complete' | 'error'>('starting');
  const bottomRef = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    if (!taskId) return;
    try {
      const result = await ragApi.getAnalysisStatus(slug, taskId);
      setMessages(result.messages);
      setStatus(result.status);
    } catch {
      setStatus('error');
    }
  }, [slug, taskId]);

  useEffect(() => {
    if (!taskId) return;
    void poll();
    const interval = setInterval(() => {
      void poll();
    }, 3000);
    return () => clearInterval(interval);
  }, [taskId, poll]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const isActive = status === 'starting' || status === 'running';

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      <div className="flex-1 overflow-y-auto max-h-[400px] space-y-3 rounded-lg border border-border bg-surface-primary p-4">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={[
              'rounded-lg px-3 py-2 text-sm max-w-[85%]',
              msg.role === 'agent'
                ? 'bg-surface-tertiary text-content-primary self-start'
                : 'bg-accent-blue/20 text-content-primary self-end ml-auto',
            ].join(' ')}
          >
            <p className="whitespace-pre-wrap">{msg.content}</p>
          </div>
        ))}

        {isActive && (
          <div className="flex items-center gap-2 text-content-tertiary">
            <Spinner size="sm" />
            <span className="text-xs">{t('analysis.agent_thinking')}</span>
          </div>
        )}

        {status === 'complete' && (
          <p className="text-xs text-accent-green font-medium">{t('analysis.complete')}</p>
        )}

        <div ref={bottomRef} />
      </div>

      {status === 'starting' && !taskId && (
        <div className="flex items-center gap-2 text-content-secondary">
          <Spinner size="sm" />
          <span className="text-sm">{t('analysis.starting')}</span>
        </div>
      )}
    </div>
  );
}
