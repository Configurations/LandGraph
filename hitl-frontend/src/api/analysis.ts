import { apiFetch } from './client';
import type { AnalysisStartResponse, AnalysisStatusResponse, AnalysisMessage } from './types';

const enc = encodeURIComponent;

export function startAnalysis(slug: string): Promise<AnalysisStartResponse> {
  return apiFetch<AnalysisStartResponse>(`/api/projects/${enc(slug)}/analysis/start`, { method: 'POST' });
}

export function getStatus(slug: string): Promise<AnalysisStatusResponse> {
  return apiFetch<AnalysisStatusResponse>(`/api/projects/${enc(slug)}/analysis/status`);
}

export function getConversation(slug: string): Promise<AnalysisMessage[]> {
  return apiFetch<AnalysisMessage[]>(`/api/projects/${enc(slug)}/analysis/conversation`);
}

export function reply(slug: string, requestId: string, response: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/projects/${enc(slug)}/analysis/reply`, {
    method: 'POST',
    body: JSON.stringify({ request_id: requestId, response }),
  });
}

export function sendMessage(slug: string, content: string): Promise<{ task_id: string; status: string }> {
  return apiFetch<{ task_id: string; status: string }>(`/api/projects/${enc(slug)}/analysis/message`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}
