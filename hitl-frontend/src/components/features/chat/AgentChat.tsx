import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChatBubble } from './ChatBubble';
import { ChatInput } from './ChatInput';
import { ChatTypingIndicator } from './ChatTypingIndicator';
import { Spinner } from '../../ui/Spinner';
import { useChatStore } from '../../../stores/chatStore';
import { useWsStore } from '../../../stores/wsStore';
import { useAuthStore } from '../../../stores/authStore';
import * as chatApi from '../../../api/chat';

interface AgentChatProps {
  teamId: string;
  agentId: string;
  className?: string;
}

export function AgentChat({
  teamId,
  agentId,
  className = '',
}: AgentChatProps): JSX.Element {
  const { t } = useTranslation();
  const messages = useChatStore((s) => s.messages);
  const loading = useChatStore((s) => s.loading);
  const loadHistory = useChatStore((s) => s.loadHistory);
  const addMessage = useChatStore((s) => s.addMessage);
  const user = useAuthStore((s) => s.user);
  const lastEvent = useWsStore((s) => s.lastEvent);

  const [sending, setSending] = useState(false);
  const [typing, setTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void loadHistory(teamId, agentId);
  }, [teamId, agentId, loadHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.type === 'chat_message' && lastEvent.data['agent_id'] === agentId) {
      void loadHistory(teamId, agentId);
      setTyping(false);
    }
    if (lastEvent.type === 'agent_typing' && lastEvent.data['agent_id'] === agentId) {
      setTyping(true);
    }
  }, [lastEvent, agentId, teamId, loadHistory]);

  const handleSend = useCallback(
    async (content: string) => {
      setSending(true);
      setTyping(true);
      try {
        const msg = await chatApi.sendMessage(teamId, agentId, content);
        addMessage(msg);
      } catch {
        // handled by apiFetch
      } finally {
        setSending(false);
      }
    },
    [teamId, agentId, addMessage],
  );

  const userEmail = user?.email ?? '';

  if (loading) {
    return (
      <div className={`flex items-center justify-center py-12 ${className}`}>
        <Spinner />
      </div>
    );
  }

  return (
    <div className={`flex flex-col h-full ${className}`}>
      <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-2">
        {messages.length === 0 && (
          <p className="text-sm text-content-tertiary text-center py-8">
            {t('chat.no_messages')}
          </p>
        )}
        {messages.map((msg) => (
          <ChatBubble
            key={msg.id}
            message={msg}
            isUser={msg.sender === userEmail}
          />
        ))}
        {typing && <ChatTypingIndicator agentName={agentId} />}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={handleSend} loading={sending} />
    </div>
  );
}
