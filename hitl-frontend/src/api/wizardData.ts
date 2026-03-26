import { apiFetch } from './client';

export interface WizardStepEntry {
  step_id: number;
  data: Record<string, unknown>;
}

export function getWizardData(slug: string): Promise<WizardStepEntry[]> {
  return apiFetch<WizardStepEntry[]>(
    `/api/projects/${encodeURIComponent(slug)}/wizard-data`,
  );
}

export function saveWizardStep(
  slug: string,
  stepId: number,
  data: Record<string, unknown>,
): Promise<WizardStepEntry[]> {
  return apiFetch<WizardStepEntry[]>(
    `/api/projects/${encodeURIComponent(slug)}/wizard-data/${stepId}`,
    { method: 'PUT', body: JSON.stringify({ data }) },
  );
}

export function deleteWizardData(slug: string): Promise<void> {
  return apiFetch<void>(
    `/api/projects/${encodeURIComponent(slug)}/wizard-data`,
    { method: 'DELETE' },
  );
}
