import { apiFetch } from './client';
import type {
  PRCreatePayload,
  PRListParams,
  PRResponse,
  PRStatusUpdatePayload,
} from './types';

export function listPRs(params?: PRListParams): Promise<PRResponse[]> {
  const query = new URLSearchParams();
  if (params?.project_id) query.set('project_id', params.project_id);
  if (params?.status) query.set('status', params.status);
  const qs = query.toString();
  return apiFetch<PRResponse[]>(`/api/pm/prs${qs ? `?${qs}` : ''}`);
}

export function createPR(data: PRCreatePayload): Promise<PRResponse> {
  return apiFetch<PRResponse>('/api/pm/prs', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function getPR(id: string): Promise<PRResponse> {
  return apiFetch<PRResponse>(`/api/pm/prs/${encodeURIComponent(id)}`);
}

export function updatePRStatus(
  id: string,
  data: PRStatusUpdatePayload,
): Promise<PRResponse> {
  return apiFetch<PRResponse>(
    `/api/pm/prs/${encodeURIComponent(id)}/status`,
    { method: 'PATCH', body: JSON.stringify(data) },
  );
}

export function mergePR(id: string): Promise<PRResponse> {
  return apiFetch<PRResponse>(
    `/api/pm/prs/${encodeURIComponent(id)}/merge`,
    { method: 'POST' },
  );
}
