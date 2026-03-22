import { apiFetch } from './client';
import type {
  IssueCreatePayload,
  IssueDetail,
  IssueListParams,
  IssueResponse,
  IssueUpdatePayload,
} from './types';

export function listIssues(params?: IssueListParams): Promise<IssueResponse[]> {
  const query = new URLSearchParams();
  if (params?.team_id) query.set('team_id', params.team_id);
  if (params?.project_id) query.set('project_id', params.project_id);
  if (params?.status) query.set('status', params.status);
  if (params?.assignee) query.set('assignee', params.assignee);
  const qs = query.toString();
  return apiFetch<IssueResponse[]>(`/api/pm/issues${qs ? `?${qs}` : ''}`);
}

export function getIssue(id: string): Promise<IssueDetail> {
  return apiFetch<IssueDetail>(`/api/pm/issues/${encodeURIComponent(id)}`);
}

export function createIssue(
  teamId: string,
  data: IssueCreatePayload,
): Promise<IssueResponse> {
  return apiFetch<IssueResponse>(
    `/api/pm/teams/${encodeURIComponent(teamId)}/issues`,
    { method: 'POST', body: JSON.stringify(data) },
  );
}

export function updateIssue(
  id: string,
  data: IssueUpdatePayload,
): Promise<IssueResponse> {
  return apiFetch<IssueResponse>(
    `/api/pm/issues/${encodeURIComponent(id)}`,
    { method: 'PATCH', body: JSON.stringify(data) },
  );
}

export function deleteIssue(id: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/api/pm/issues/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  );
}

export function bulkCreate(
  teamId: string,
  data: IssueCreatePayload[],
): Promise<IssueResponse[]> {
  return apiFetch<IssueResponse[]>(
    `/api/pm/teams/${encodeURIComponent(teamId)}/issues/bulk`,
    { method: 'POST', body: JSON.stringify(data) },
  );
}

export function searchIssues(
  teamId: string,
  query: string,
): Promise<IssueResponse[]> {
  const qs = new URLSearchParams({ q: query }).toString();
  return apiFetch<IssueResponse[]>(
    `/api/pm/teams/${encodeURIComponent(teamId)}/issues/search?${qs}`,
  );
}
