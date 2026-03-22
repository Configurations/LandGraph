import { apiFetch } from './client';
import type { PMNotification } from './types';

export function listNotifications(): Promise<PMNotification[]> {
  return apiFetch<PMNotification[]>('/api/pm/notifications');
}

export function markRead(id: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/api/pm/notifications/${encodeURIComponent(id)}/read`,
    { method: 'POST' },
  );
}

export function markAllRead(): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>('/api/pm/notifications/read-all', {
    method: 'POST',
  });
}

export function getUnreadCount(): Promise<{ count: number }> {
  return apiFetch<{ count: number }>('/api/pm/notifications/unread-count');
}
