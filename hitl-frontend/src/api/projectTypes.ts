import { apiFetch } from './client';
import type { ProjectTypeResponse } from './types';

export async function listProjectTypes(_teamId?: string): Promise<ProjectTypeResponse[]> {
  try {
    return await apiFetch<ProjectTypeResponse[]>('/api/project-types');
  } catch {
    return [];
  }
}

export function getProjectType(typeId: string): Promise<ProjectTypeResponse> {
  return apiFetch<ProjectTypeResponse>(
    `/api/project-types/${encodeURIComponent(typeId)}`,
  );
}

export function applyProjectType(
  slug: string,
  typeId: string,
): Promise<{ applied: boolean }> {
  return apiFetch<{ applied: boolean }>(
    `/api/projects/${encodeURIComponent(slug)}/apply-type`,
    { method: 'POST', body: JSON.stringify({ type_id: typeId }) },
  );
}
