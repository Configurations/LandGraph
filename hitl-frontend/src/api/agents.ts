import { apiFetch } from './client';
import type { AgentInfo } from './types';

export function listAgents(teamId: string): Promise<AgentInfo[]> {
  return apiFetch<AgentInfo[]>(`/api/teams/${encodeURIComponent(teamId)}/agents`);
}
