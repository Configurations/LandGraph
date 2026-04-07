import { apiFetch } from './client';
import type {
  BranchDiffFile,
  BranchInfo,
  DeliverableDetail,
  DeliverableListParams,
  DeliverableResponse,
  RemarkResponse,
} from './types';

export function listDeliverables(
  slug: string,
  params?: DeliverableListParams,
): Promise<DeliverableResponse[]> {
  const query = new URLSearchParams();
  if (params?.phase) query.set('phase', params.phase);
  if (params?.status) query.set('status', params.status);
  if (params?.agent_id) query.set('agent_id', params.agent_id);
  const qs = query.toString();
  const path = `/api/projects/${encodeURIComponent(slug)}/deliverables${qs ? `?${qs}` : ''}`;
  return apiFetch<DeliverableResponse[]>(path);
}

export function getDeliverable(id: string): Promise<DeliverableDetail> {
  return apiFetch<DeliverableDetail>(`/api/deliverables/${encodeURIComponent(id)}`);
}

export function validateDeliverable(
  id: string,
  verdict: 'approved' | 'rejected',
  comment?: string,
): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/deliverables/${encodeURIComponent(id)}/validate`, {
    method: 'POST',
    body: JSON.stringify({ verdict, comment }),
  });
}

export function submitRemark(id: string, comment: string): Promise<RemarkResponse> {
  return apiFetch<RemarkResponse>(`/api/deliverables/${encodeURIComponent(id)}/remarks`, {
    method: 'POST',
    body: JSON.stringify({ comment }),
  });
}

export function listRemarks(id: string): Promise<RemarkResponse[]> {
  return apiFetch<RemarkResponse[]>(`/api/deliverables/${encodeURIComponent(id)}/remarks`);
}

export function updateContent(id: string, content: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/deliverables/${encodeURIComponent(id)}/content`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

export function listBranches(slug: string): Promise<BranchInfo[]> {
  return apiFetch<BranchInfo[]>(`/api/projects/${encodeURIComponent(slug)}/branches`);
}

export function getBranchDiff(slug: string, branch: string): Promise<BranchDiffFile[]> {
  return apiFetch<BranchDiffFile[]>(
    `/api/projects/${encodeURIComponent(slug)}/branches/${encodeURIComponent(branch)}/diff`,
  );
}

export function reviseDeliverable(id: number, comment: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/deliverables/${id}/revise`, {
    method: 'POST',
    body: JSON.stringify({ comment }),
  });
}
