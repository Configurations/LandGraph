import { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { Spinner } from '../../ui/Spinner';
import { ChatInput } from '../chat/ChatInput';
import { ChatTypingIndicator } from '../chat/ChatTypingIndicator';
import { AnalysisChatMessage } from './AnalysisChatMessage';
import { AnalysisQuestionBanner } from './AnalysisQuestionBanner';
import { useAnalysisStore } from '../../../stores/analysisStore';
import { useWsStore } from '../../../stores/wsStore';
import { useProjectStore } from '../../../stores/projectStore';
import * as analysisApi from '../../../api/analysis';
import type { AnalysisMessage, WebSocketEvent } from '../../../api/types';

const POLL_INTERVAL = 5_000;
const THREAD_PREFIX = 'onboarding-';

interface WizardStepAnalysisProps {
  className?: string;
}

export function WizardStepAnalysis({ className = '' }: WizardStepAnalysisProps): JSX.Element {
  const { t } = useTranslation();
  const slug = useProjectStore((s) => s.wizardData.slug);
  const bottomRef = useRef<HTMLDivElement>(null);

  const {
    status, taskId, threadId, messages, pendingQuestion,
    setStatus, setTaskId, setThreadId, addMessage, setMessages, setPendingQuestion, reset,
  } = useAnalysisStore();

  const wsConnected = useWsStore((s) => s.connected);
  const lastEvent = useWsStore((s) => s.lastEvent);

  // ── Init: check status on mount ──
  useEffect(() => {
    if (!slug) return;
    reset();
    setThreadId(`${THREAD_PREFIX}${slug}`);

    analysisApi.getStatus(slug).then((res) => {
      if (res.status === 'not_started') {
        setStatus('idle');
      } else {
        const mapped = res.status === 'waiting_input' ? 'waiting_input'
          : res.status === 'completed' ? 'completed'
          : res.status === 'failed' ? 'failed'
          : 'running';
        setStatus(mapped);
        if (res.task_id) setTaskId(res.task_id);
        if (res.has_pending_question && res.pending_request_id) {
          if (res.pending_request_type === 'approval') {
            setStatus('completed');
            return;
          }
          setPendingQuestion({ requestId: res.pending_request_id, prompt: '' });
        }
        analysisApi.getConversation(slug).then(setMessages).catch(() => {});
      }
    }).catch(() => setStatus('idle'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  // ── Start analysis ──
  const handleStart = useCallback(async () => {
    if (!slug) return;
    setStatus('starting');
    try {
      const res = await analysisApi.startAnalysis(slug);
      setTaskId(res.task_id);
      setStatus('running');
    } catch {
      setStatus('failed');
    }
  }, [slug, setStatus, setTaskId]);

  // ── WS event handler ──
  useEffect(() => {
    if (!lastEvent || !taskId || !threadId) return;
    const ev: WebSocketEvent = lastEvent;
    const d = ev.data ?? {};

    if (ev.type === 'task_progress' && d.task_id === taskId) {
      const raw = d.data as string | Record<string, unknown>;
      const content = typeof raw === 'string' ? raw : (String((raw as Record<string, unknown>)?.data ?? JSON.stringify(raw)));
      addMessage({
        id: `ws-prog-${Date.now()}`,
        sender: 'agent',
        type: 'progress',
        content,
        agent_id: typeof raw === 'object' ? String((raw as Record<string, unknown>)?.agent_id ?? '') : undefined,
        created_at: new Date().toISOString(),
      });
    }

    if (ev.type === 'new_question' && d.thread_id === threadId) {
      // Approval = onboarding complete, show Next button
      if (d.request_type === 'approval') {
        setStatus('completed');
        return;
      }
      const msg: AnalysisMessage = {
        id: `ws-q-${String(d.id ?? Date.now())}`,
        sender: 'agent',
        type: 'question',
        content: typeof d.prompt === 'string' ? d.prompt : '',
        agent_id: typeof d.agent_id === 'string' ? d.agent_id : undefined,
        request_id: String(d.id ?? ''),
        status: 'pending',
        created_at: new Date().toISOString(),
      };
      addMessage(msg);
      setPendingQuestion({ requestId: msg.request_id!, prompt: msg.content });
      setStatus('waiting_input');
    }

    if (ev.type === 'question_answered' && pendingQuestion && String(d.request_id) === pendingQuestion.requestId) {
      setPendingQuestion(null);
      setStatus('running');
    }

    if (ev.type === 'task_artifact' && d.task_id === taskId && slug) {
      analysisApi.getConversation(slug).then(setMessages).catch(() => {});
    }

    // Refresh conversation to get avatars for WS messages
    if ((ev.type === 'task_progress' || ev.type === 'new_question') && slug) {
      setTimeout(() => {
        analysisApi.getConversation(slug).then(setMessages).catch(() => {});
      }, 500);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  // ── Polling fallback when WS disconnected ──
  useEffect(() => {
    if (wsConnected || !slug || status === 'idle' || status === 'completed' || status === 'failed') return;
    const interval = setInterval(() => {
      analysisApi.getConversation(slug).then(setMessages).catch(() => {});
      analysisApi.getStatus(slug).then((res) => {
        if (res.status === 'completed') setStatus('completed');
        else if (res.status === 'failed') setStatus('failed');
        else if (res.has_pending_question && res.pending_request_id) {
          setPendingQuestion({ requestId: res.pending_request_id, prompt: '' });
          setStatus('waiting_input');
        }
        if (res.task_id && res.task_id !== taskId) setTaskId(res.task_id);
      }).catch(() => {});
    }, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [wsConnected, slug, status, taskId, setMessages, setStatus, setPendingQuestion, setTaskId]);

  // ── Auto-scroll ──
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ── Send handler ──
  const handleSend = useCallback(async (text: string) => {
    if (!slug) return;

    if (pendingQuestion) {
      addMessage({
        id: `opt-reply-${Date.now()}`,
        sender: 'user',
        type: 'reply',
        content: text,
        request_id: pendingQuestion.requestId,
        created_at: new Date().toISOString(),
      });
      setPendingQuestion(null);
      setStatus('running');
      await analysisApi.reply(slug, pendingQuestion.requestId, text).catch(() => {});
    } else {
      addMessage({
        id: `opt-msg-${Date.now()}`,
        sender: 'user',
        type: 'reply',
        content: text,
        created_at: new Date().toISOString(),
      });
      addMessage({
        id: `sys-${Date.now()}`,
        sender: 'system',
        type: 'system',
        content: t('analysis.relaunching'),
        created_at: new Date().toISOString(),
      });
      setStatus('starting');
      try {
        const res = await analysisApi.sendMessage(slug, text);
        setTaskId(res.task_id);
        setStatus('running');
      } catch {
        setStatus('failed');
      }
    }
  }, [slug, pendingQuestion, t, addMessage, setPendingQuestion, setStatus, setTaskId]);

  const isActive = status === 'running' || status === 'starting';
  const inputDisabled = status === 'completed' || status === 'failed' || status === 'idle' || status === 'starting';

  // Extract indexation progress from messages
  const indexProgress = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.sender !== 'agent') continue;
      const match = m.content.match(/Indexation documents\s*:\s*(\d+)\/(\d+)\s*chunks\s*\((\d+)%\)/);
      if (match) return { done: Number(match[1]), total: Number(match[2]), pct: Number(match[3]) };
      // If we see the synthesis (📄), indexation is done
      if (m.content.startsWith('📄')) return null;
    }
    return null;
  })();

  return (
    <div className={`flex flex-col max-w-5xl h-[calc(100vh-12rem)] ${className}`}>
      <h3 className="text-sm font-semibold text-content-primary mb-2">{t('analysis.title')}</h3>

      {status === 'idle' && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <p className="text-sm text-content-tertiary">{t('analysis.conversation_empty')}</p>
          <Button onClick={() => void handleStart()}>{t('analysis.start')}</Button>
        </div>
      )}

      {status === 'starting' && !messages.length && (
        <div className="flex-1 flex items-center justify-center gap-2 text-content-secondary">
          <Spinner size="sm" />
          <span className="text-sm">{t('analysis.starting')}</span>
        </div>
      )}

      {status !== 'idle' && (status !== 'starting' || messages.length > 0) && (
        <>
          {indexProgress && (
            <div className="mb-3">
              <div className="flex items-center justify-between text-xs text-content-tertiary mb-1">
                <span>Indexation documents</span>
                <span>{indexProgress.done}/{indexProgress.total} chunks ({indexProgress.pct}%)</span>
              </div>
              <div className="w-full h-2 bg-surface-tertiary rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent-blue rounded-full transition-all duration-300"
                  style={{ width: `${indexProgress.pct}%` }}
                />
              </div>
            </div>
          )}
          <div className="flex-1 overflow-y-auto flex flex-col gap-2 rounded-lg border border-border bg-surface-primary p-4">
            {messages.map((msg) => (
              <AnalysisChatMessage
                key={msg.id}
                message={msg}
                onReply={(requestId, response) => {
                  void analysisApi.reply(slug, requestId, response).then(() => {
                    setPendingQuestion(null);
                    setStatus('running');
                    analysisApi.getConversation(slug).then(setMessages).catch(() => {});
                  });
                }}
              />
            ))}
            {isActive && <ChatTypingIndicator agentName="Orchestrateur" />}
            <div ref={bottomRef} />
          </div>

          {pendingQuestion && <AnalysisQuestionBanner />}

          {!inputDisabled && (
            <ChatInput
              onSend={(text) => void handleSend(text)}
              placeholder={
                pendingQuestion ? t('analysis.reply_placeholder') : t('analysis.message_placeholder')
              }
            />
          )}

          {(status === 'completed' || status === 'failed') && (
            <div className="flex items-center justify-between px-3 py-2">
              <p className="text-xs text-content-tertiary">
                {status === 'completed' ? t('analysis.result_success') : t('analysis.result_failure')}
              </p>
              {status === 'failed' && (
                <Button size="sm" variant="ghost" onClick={() => void handleStart()}>
                  {t('analysis.relaunch')}
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
