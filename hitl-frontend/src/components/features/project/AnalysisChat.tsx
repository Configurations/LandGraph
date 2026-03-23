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
  const [status, setStatus] = useState<string>('starting');
  const bottomRef = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    if (!taskId) return;
    try {
      const result = await ragApi.getAnalysisStatus(slug, taskId);
      const events = result.events ?? [];
      const msgs: ConversationMessage[] = events
        .filter((e) => e.event_type === 'progress')
        .map((e, i) => ({
          id: i,
          project_slug: slug,
          task_id: taskId,
          sender: 'agent',
          content: typeof e.data === 'string' ? e.data : JSON.stringify(e.data),
          created_at: e.created_at,
        }));
      setMessages(msgs);

      const s = result.status;
      if (s === 'success' || s === 'failure' || s === 'timeout') {
        setStatus('complete');
      } else if (s === 'running' || s === 'waiting_hitl') {
        setStatus('running');
      }
    } catch {
      setStatus('error');
    }
  }, [slug, taskId]);

  useEffect(() => {
    if (!taskId) return;
    void poll();
    const interval = setInterval(() => void poll(), 3000);
    return () => clearInterval(interval);
  }, [taskId, poll]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const isActive = status === 'starting' || status === 'running';

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      <div className="flex-1 overflow-y-auto max-h-[400px] space-y-3 rounded-lg border border-border bg-surface-primary p-4">
        {messages.length === 0 && !isActive && (
          <p className="text-xs text-content-quaternary">{t('analysis.complete')}</p>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className="rounded-lg px-3 py-2 text-sm max-w-[85%] bg-surface-tertiary text-content-primary"
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

        <div ref={bottomRef} />
      </div>

      {status === 'starting' && !taskId && (
        <div className="flex items-center gap-2 text-content-secondary">
          <Spinner size="sm" />
          <span className="text-sm">{t('analysis.starting')}</span>
        </div>
      )}

      {status === 'error' && (
        <p className="text-xs text-content-tertiary">{t('dashboard.dispatcher_offline')}</p>
      )}
    </div>
  );
}
