import { apiFetch } from './client';
import type { PulseResponse } from './types';

export function getPulse(teamId?: string, projectId?: string): Promise<PulseResponse> {
  const query = new URLSearchParams();
  if (teamId) query.set('team_id', teamId);
  if (projectId) query.set('project_id', projectId);
  const qs = query.toString();
  return apiFetch<PulseResponse>(`/api/pm/pulse${qs ? `?${qs}` : ''}`);
}
