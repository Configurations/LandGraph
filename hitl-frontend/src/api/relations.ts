import { apiFetch } from './client';
import type { RelationCreatePayload, RelationResponse } from './types';

export function listRelations(issueId: string): Promise<RelationResponse[]> {
  return apiFetch<RelationResponse[]>(
    `/api/pm/issues/${encodeURIComponent(issueId)}/relations`,
  );
}

export function createRelation(
  issueId: string,
  data: RelationCreatePayload,
): Promise<RelationResponse> {
  return apiFetch<RelationResponse>(
    `/api/pm/issues/${encodeURIComponent(issueId)}/relations`,
    { method: 'POST', body: JSON.stringify(data) },
  );
}

export function deleteRelation(id: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/api/pm/relations/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  );
}

export function bulkCreateRelations(
  data: Array<{ issue_id: string } & RelationCreatePayload>,
): Promise<RelationResponse[]> {
  return apiFetch<RelationResponse[]>('/api/pm/relations/bulk', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
