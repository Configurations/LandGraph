import { apiFetch, getToken } from './client';
import type {
  UploadResponse,
  UploadedFile,
  RagSearchResult,
  AnalysisStartResponse,
  AnalysisStatusResponse,
  ConversationMessage,
} from './types';

export async function uploadDocument(slug: string, file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const token = getToken();
  const headers = new Headers();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`/api/projects/${encodeURIComponent(slug)}/upload`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text);
  }

  return (await response.json()) as UploadResponse;
}

export function listUploads(slug: string): Promise<UploadedFile[]> {
  return apiFetch<UploadedFile[]>(`/api/projects/${encodeURIComponent(slug)}/uploads`);
}

export function deleteUpload(slug: string, filename: string): Promise<void> {
  return apiFetch<void>(
    `/api/projects/${encodeURIComponent(slug)}/uploads/${encodeURIComponent(filename)}`,
    { method: 'DELETE' },
  );
}

export function searchRag(slug: string, query: string, topK?: number): Promise<RagSearchResult[]> {
  const params: Record<string, string> = { query };
  if (topK !== undefined) params.top_k = String(topK);
  return apiFetch<RagSearchResult[]>(`/api/projects/${encodeURIComponent(slug)}/search`, {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export function startAnalysis(slug: string, teamId: string): Promise<AnalysisStartResponse> {
  return apiFetch<AnalysisStartResponse>(
    `/api/projects/${encodeURIComponent(slug)}/analysis/start`,
    { method: 'POST', body: JSON.stringify({ team_id: teamId }) },
  );
}

export function getAnalysisStatus(slug: string, taskId: string): Promise<AnalysisStatusResponse> {
  return apiFetch<AnalysisStatusResponse>(
    `/api/projects/${encodeURIComponent(slug)}/analysis/status?task_id=${encodeURIComponent(taskId)}`,
  );
}

export function getConversation(slug: string): Promise<ConversationMessage[]> {
  return apiFetch<ConversationMessage[]>(
    `/api/projects/${encodeURIComponent(slug)}/analysis/conversation`,
  );
}
