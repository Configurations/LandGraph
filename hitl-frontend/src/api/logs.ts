import { apiFetch, getToken } from './client';

/**
 * Build the SSE URL for log streaming (token passed as query param
 * because EventSource doesn't support custom headers).
 */
export function buildStreamUrl(container: string, tail: number = 200): string {
  const token = getToken();
  const params = new URLSearchParams({
    container,
    tail: String(tail),
  });
  if (token) {
    params.set('token', token);
  }
  return `/api/logs/stream?${params}`;
}

export function listContainers(): Promise<string[]> {
  return apiFetch<string[]>('/api/logs/containers');
}
