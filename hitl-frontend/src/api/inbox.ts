import { apiFetch } from './client';
import type { PMNotification } from './types';

export async function listNotifications(): Promise<PMNotification[]> {
  try {
    return await apiFetch<PMNotification[]>('/api/pm/inbox');
  } catch {
    return [];
  }
}

export function markRead(id: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/api/pm/inbox/${encodeURIComponent(id)}/read`,
    { method: 'PUT' },
  );
}

export function markAllRead(): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>('/api/pm/inbox/read-all', {
    method: 'PUT',
  });
}

export async function getUnreadCount(): Promise<number> {
  try {
    const data = await apiFetch<{ count: number }>('/api/pm/inbox/count');
    return data.count ?? 0;
  } catch {
    return 0;
  }
}
