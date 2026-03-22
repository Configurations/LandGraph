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
): Promise<ChatMessage> {
  return apiFetch<ChatMessage>(
    `/api/teams/${encodeURIComponent(teamId)}/agents/${encodeURIComponent(agentId)}/chat`,
    {
      method: 'POST',
      body: JSON.stringify({ message }),
    },
  );
}

export function clearChat(teamId: string, agentId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/api/teams/${encodeURIComponent(teamId)}/agents/${encodeURIComponent(agentId)}/chat`,
    { method: 'DELETE' },
  );
}
