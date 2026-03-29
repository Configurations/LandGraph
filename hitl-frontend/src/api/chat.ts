import { apiFetch } from './client';
import type { ChatMessage } from './types';

export function getChatHistory(teamId: string, agentId: string): Promise<ChatMessage[]> {
  return apiFetch<ChatMessage[]>(
    `/api/teams/${encodeURIComponent(teamId)}/agents/${encodeURIComponent(agentId)}/chat`,
  );
}

export function sendMessage(
  teamId: string,
  agentId: string,
  message: string,
  projectId?: string,
  chatId?: string,
): Promise<ChatMessage> {
  const body: Record<string, string> = { message };
  if (projectId) body.project_id = projectId;
  if (chatId) body.chat_id = chatId;
  return apiFetch<ChatMessage>(
    `/api/teams/${encodeURIComponent(teamId)}/agents/${encodeURIComponent(agentId)}/chat`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}

export interface ChatContext {
  project_id: string;
  project_name: string;
  chats: {
    id: string;
    type: string;
    agents: string[];
    agent_prompts: Record<string, string>;
  }[];
}

export function getChatContexts(): Promise<ChatContext[]> {
  return apiFetch<ChatContext[]>('/api/chat-contexts');
}

export function clearChat(teamId: string, agentId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/api/teams/${encodeURIComponent(teamId)}/agents/${encodeURIComponent(agentId)}/chat`,
    { method: 'DELETE' },
  );
}
