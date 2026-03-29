import { apiFetch } from './client';
import type { PhaseFile, PhaseFileContent, ProjectTypeResponse } from './types';

export async function listProjectTypes(_teamId?: string): Promise<ProjectTypeResponse[]> {
  try {
    return await apiFetch<ProjectTypeResponse[]>('/api/project-types');
  } catch {
    return [];
  }
}

export function getProjectType(typeId: string): Promise<ProjectTypeResponse> {
  return apiFetch<ProjectTypeResponse>(
    `/api/project-types/${encodeURIComponent(typeId)}`,
  );
}

export interface ApplyProjectTypeResult {
  ok: boolean;
  workflow_ids: number[];
  orchestrator_prompt: string | null;
}

export async function fetchPhaseFiles(
  typeId: string,
  wfFilename: string,
): Promise<PhaseFile[]> {
  try {
    return await apiFetch<PhaseFile[]>(
      `/api/project-types/${encodeURIComponent(typeId)}/workflows/${encodeURIComponent(wfFilename)}/phase-files`,
    );
  } catch {
    return [];
  }
}

export async function fetchPhaseFileContent(
  typeId: string,
  wfFilename: string,
  phaseId: string,
): Promise<PhaseFileContent | null> {
  try {
    return await apiFetch<PhaseFileContent>(
      `/api/project-types/${encodeURIComponent(typeId)}/workflows/${encodeURIComponent(wfFilename)}/phase-files/${encodeURIComponent(phaseId)}`,
    );
  } catch {
    return null;
  }
}

export async function fetchResolvedPhases(
  typeId: string,
  wfFilename: string,
): Promise<any[]> {
  try {
    return await apiFetch<any[]>(
      `/api/project-types/${encodeURIComponent(typeId)}/workflows/${encodeURIComponent(wfFilename)}/resolved-phases`,
    );
  } catch {
    return [];
  }
}

export function applyProjectType(
  slug: string,
  typeId: string,
  workflowFilename?: string,
): Promise<ApplyProjectTypeResult> {
  return apiFetch<ApplyProjectTypeResult>(
    `/api/projects/${encodeURIComponent(slug)}/apply-type/${encodeURIComponent(typeId)}`,
    {
      method: 'POST',
      body: JSON.stringify({
        workflow_filename: workflowFilename ?? '',
      }),
    },
  );
}
