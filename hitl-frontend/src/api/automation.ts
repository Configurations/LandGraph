import { apiFetch } from './client';
import type {
  AgentConfidence,
  AutomationRule,
  AutomationRuleCreatePayload,
  AutomationStats,
} from './types';

const enc = encodeURIComponent;

export function listRules(slug: string): Promise<AutomationRule[]> {
  return apiFetch<AutomationRule[]>(`/api/projects/${enc(slug)}/automation/rules`);
}

export function createRule(
  slug: string,
  payload: AutomationRuleCreatePayload,
): Promise<AutomationRule> {
  return apiFetch<AutomationRule>(`/api/projects/${enc(slug)}/automation/rules`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateRule(
  slug: string,
  ruleId: string,
  payload: Partial<AutomationRuleCreatePayload & { enabled: boolean }>,
): Promise<AutomationRule> {
  return apiFetch<AutomationRule>(
    `/api/projects/${enc(slug)}/automation/rules/${enc(ruleId)}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
  );
}

export function deleteRule(slug: string, ruleId: string): Promise<void> {
  return apiFetch<void>(
    `/api/projects/${enc(slug)}/automation/rules/${enc(ruleId)}`,
    { method: 'DELETE' },
  );
}

export function getStats(slug: string): Promise<AutomationStats> {
  return apiFetch<AutomationStats>(`/api/projects/${enc(slug)}/automation/stats`);
}

export function getAgentConfidence(
  slug: string,
  agentId: string,
): Promise<AgentConfidence> {
  return apiFetch<AgentConfidence>(
    `/api/projects/${enc(slug)}/automation/confidence/${enc(agentId)}`,
  );
}
