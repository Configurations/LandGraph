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
import * as agentsApi from '../../../api/agents';
import type { AgentInfo } from '../../../api/types';

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
  const [agentInfo, setAgentInfo] = useState<AgentInfo | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Chat context (project + chat)
  const [contexts, setContexts] = useState<chatApi.ChatContext[]>([]);
  const [selectedProject, setSelectedProject] = useState('');
  const [selectedChat, setSelectedChat] = useState('');

  useEffect(() => {
    void loadHistory(teamId, agentId);
    agentsApi.listAgents(teamId).then((agents) => {
      const found = agents.find((a) => a.id === agentId);
      if (found) setAgentInfo(found);
    }).catch(() => {/* ignore */});
    // Load chat contexts
    chatApi.getChatContexts().then((ctxs) => {
      // Filter to contexts that include this agent
      const filtered = ctxs.map((p) => ({
        ...p,
        chats: p.chats.filter((c) => c.agents.includes(agentId)),
      })).filter((p) => p.chats.length > 0);
      setContexts(filtered);
    }).catch(() => {/* ignore */});
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
        const msg = await chatApi.sendMessage(
          teamId, agentId, content,
          selectedProject || undefined,
          selectedChat || undefined,
        );
        addMessage(msg);
      } catch {
        // handled by apiFetch
      } finally {
        setSending(false);
      }
    },
    [teamId, agentId, addMessage, selectedProject, selectedChat],
  );

  const handleProjectChange = (value: string) => {
    setSelectedProject(value);
    setSelectedChat('');
  };

  const currentProjectCtx = contexts.find((p) => p.project_id === selectedProject);
  const availableChats = currentProjectCtx?.chats ?? [];

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
      {/* Context selector */}
      {contexts.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-surface-secondary text-xs">
          <span className="text-content-secondary font-medium">Contexte:</span>
          <select
            className="px-2 py-1 rounded border border-border bg-surface text-content text-xs"
            value={selectedProject}
            onChange={(e) => handleProjectChange(e.target.value)}
          >
            <option value="">Sans contexte</option>
            {contexts.map((p) => (
              <option key={p.project_id} value={p.project_id}>{p.project_name}</option>
            ))}
          </select>
          {selectedProject && availableChats.length > 0 && (
            <select
              className="px-2 py-1 rounded border border-border bg-surface text-content text-xs"
              value={selectedChat}
              onChange={(e) => setSelectedChat(e.target.value)}
            >
              <option value="">Choisir un chat</option>
              {availableChats.map((c) => (
                <option key={c.id} value={c.id}>{c.id} ({c.type})</option>
              ))}
            </select>
          )}
        </div>
      )}
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
            agentName={agentInfo?.name}
            agentAvatarUrl={agentInfo?.avatar_url}
          />
        ))}
        {typing && <ChatTypingIndicator agentName={agentInfo?.name || agentId} />}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={handleSend} loading={sending} />
    </div>
  );
}
