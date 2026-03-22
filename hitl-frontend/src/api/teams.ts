import { apiFetch } from './client';
import type { InviteMemberPayload, MemberResponse, TeamResponse } from './types';

export function listTeams(): Promise<TeamResponse[]> {
  return apiFetch<TeamResponse[]>('/api/teams');
}

export function listMembers(teamId: string): Promise<MemberResponse[]> {
  return apiFetch<MemberResponse[]>(`/api/teams/${encodeURIComponent(teamId)}/members`);
}

export function inviteMember(
  teamId: string,
  payload: InviteMemberPayload,
): Promise<{ ok: boolean; id: string }> {
  return apiFetch<{ ok: boolean; id: string }>(
    `/api/teams/${encodeURIComponent(teamId)}/members`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function removeMember(
  teamId: string,
  userId: string,
): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/api/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`,
    { method: 'DELETE' },
  );
}
