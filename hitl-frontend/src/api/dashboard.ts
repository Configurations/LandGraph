import { apiFetch } from './client';
import type { ActiveTask, CostSummary, OverviewData } from './types';

export async function getActiveTasks(teamId?: string): Promise<ActiveTask[]> {
  const qs = teamId ? `?team_id=${encodeURIComponent(teamId)}` : '';
  try {
    return await apiFetch<ActiveTask[]>(`/api/dashboard/active-tasks${qs}`);
  } catch {
    return [];
  }
}

export async function getProjectCosts(slug: string): Promise<CostSummary[]> {
  try {
    const data = await apiFetch<{ by_phase: CostSummary[] }>(
      `/api/dashboard/costs/${encodeURIComponent(slug)}`,
    );
    return data.by_phase ?? [];
  } catch {
    return [];
  }
}

export async function getOverview(teamId?: string): Promise<OverviewData> {
  const qs = teamId ? `?team_id=${encodeURIComponent(teamId)}` : '';
  try {
    return await apiFetch<OverviewData>(`/api/dashboard/overview${qs}`);
  } catch {
    return { pending_questions: 0, active_tasks: 0, total_cost: 0 };
  }
}
