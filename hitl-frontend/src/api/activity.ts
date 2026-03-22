import { apiFetch } from './client';
import type { ActivityEntry } from './types';

export function getProjectActivity(
  projectId: string,
  limit?: number,
): Promise<ActivityEntry[]> {
  const qs = limit !== undefined ? `?limit=${limit}` : '';
  return apiFetch<ActivityEntry[]>(
    `/api/pm/projects/${encodeURIComponent(projectId)}/activity${qs}`,
  );
}
