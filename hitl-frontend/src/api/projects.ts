import { apiFetch } from './client';
import type {
  ProjectResponse,
  CreateProjectPayload,
  SlugCheckResponse,
  GitTestPayload,
  GitTestResponse,
  GitStatusResponse,
} from './types';

export function createProject(data: CreateProjectPayload): Promise<ProjectResponse> {
  return apiFetch<ProjectResponse>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function listProjects(): Promise<ProjectResponse[]> {
  return apiFetch<ProjectResponse[]>('/api/projects');
}

export function getProject(slug: string): Promise<ProjectResponse> {
  return apiFetch<ProjectResponse>(`/api/projects/${encodeURIComponent(slug)}`);
}

export function checkSlug(slug: string): Promise<SlugCheckResponse> {
  return apiFetch<SlugCheckResponse>(`/api/projects/${encodeURIComponent(slug)}/check-slug`, {
    method: 'POST',
  });
}

export function testGitConnection(slug: string, config: GitTestPayload): Promise<GitTestResponse> {
  return apiFetch<GitTestResponse>(`/api/projects/${encodeURIComponent(slug)}/git/test`, {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export function initGit(slug: string, config: GitTestPayload): Promise<GitTestResponse> {
  return apiFetch<GitTestResponse>(`/api/projects/${encodeURIComponent(slug)}/git/init`, {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export function getGitStatus(slug: string): Promise<GitStatusResponse> {
  return apiFetch<GitStatusResponse>(`/api/projects/${encodeURIComponent(slug)}/git/status`);
}
