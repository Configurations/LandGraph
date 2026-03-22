import { apiFetch } from './client';
import type { ActiveTask, CostSummary, OverviewData } from './types';

export function getActiveTasks(teamId?: string): Promise<ActiveTask[]> {
  const qs = teamId ? `?team_id=${encodeURIComponent(teamId)}` : '';
  return apiFetch<ActiveTask[]>(`/api/dashboard/tasks${qs}`);
}

export function getProjectCosts(slug: string): Promise<CostSummary[]> {
  return apiFetch<CostSummary[]>(
    `/api/projects/${encodeURIComponent(slug)}/costs`,
  );
}

export function getOverview(teamId?: string): Promise<OverviewData> {
  const qs = teamId ? `?team_id=${encodeURIComponent(teamId)}` : '';
  return apiFetch<OverviewData>(`/api/dashboard/overview${qs}`);
}
