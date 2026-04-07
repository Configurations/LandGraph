import { apiFetch } from './client';
import type {
  PhaseStatus,
  ProjectWorkflowCreatePayload,
  ProjectWorkflowResponse,
  WorkflowPhasesResponse,
  WorkflowStatusResponse,
} from './types';

const enc = encodeURIComponent;

export function getWorkflowStatus(slug: string): Promise<WorkflowStatusResponse> {
  return apiFetch<WorkflowStatusResponse>(`/api/projects/${enc(slug)}/workflow`);
}

export function getPhaseDetail(slug: string, phase: string): Promise<PhaseStatus> {
  return apiFetch<PhaseStatus>(
    `/api/projects/${enc(slug)}/workflow/phases/${enc(phase)}`,
  );
}

export function listProjectWorkflows(slug: string): Promise<ProjectWorkflowResponse[]> {
  return apiFetch<ProjectWorkflowResponse[]>(`/api/projects/${enc(slug)}/workflows`);
}

export function createProjectWorkflow(
  slug: string,
  payload: ProjectWorkflowCreatePayload,
): Promise<ProjectWorkflowResponse> {
  return apiFetch<ProjectWorkflowResponse>(`/api/projects/${enc(slug)}/workflows`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getProjectWorkflow(
  slug: string,
  workflowId: string,
): Promise<ProjectWorkflowResponse> {
  return apiFetch<ProjectWorkflowResponse>(
    `/api/projects/${enc(slug)}/workflows/${enc(workflowId)}`,
  );
}

export function activateWorkflow(slug: string, workflowId: string): Promise<ProjectWorkflowResponse> {
  return apiFetch<ProjectWorkflowResponse>(
    `/api/projects/${enc(slug)}/workflows/${enc(workflowId)}/activate`,
    { method: 'POST' },
  );
}

export function pauseWorkflow(slug: string, workflowId: string): Promise<ProjectWorkflowResponse> {
  return apiFetch<ProjectWorkflowResponse>(
    `/api/projects/${enc(slug)}/workflows/${enc(workflowId)}/pause`,
    { method: 'POST' },
  );
}

export function completeWorkflow(slug: string, workflowId: string): Promise<ProjectWorkflowResponse> {
  return apiFetch<ProjectWorkflowResponse>(
    `/api/projects/${enc(slug)}/workflows/${enc(workflowId)}/complete`,
    { method: 'POST' },
  );
}

export function relaunchWorkflow(slug: string, workflowId: string): Promise<ProjectWorkflowResponse> {
  return apiFetch<ProjectWorkflowResponse>(
    `/api/projects/${enc(slug)}/workflows/${enc(workflowId)}/relaunch`,
    { method: 'POST' },
  );
}

export function startWorkflow(slug: string, workflowId: number): Promise<{ ok: boolean; dispatched: string[] }> {
  return apiFetch<{ ok: boolean; dispatched: string[] }>(
    `/api/projects/${encodeURIComponent(slug)}/workflows/${workflowId}/start`,
    { method: 'POST' },
  );
}

export function resetPhaseGroup(
  slug: string,
  workflowId: number,
  phaseId: number,
): Promise<{ ok: boolean; phase_id: number; deleted_files: number }> {
  return apiFetch<{ ok: boolean; phase_id: number; deleted_files: number }>(
    `/api/projects/${enc(slug)}/workflows/${workflowId}/phases/${phaseId}/reset`,
    { method: 'POST' },
  );
}

export function getWorkflowPhases(slug: string, workflowId: number): Promise<WorkflowPhasesResponse> {
  return apiFetch<WorkflowPhasesResponse>(
    `/api/projects/${encodeURIComponent(slug)}/workflows/${workflowId}/phases`,
  );
}
