import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useDeliverableStore } from '../../src/stores/deliverableStore';
import type { DeliverableResponse } from '../../src/api/types';

// Mock the deliverables API
vi.mock('../../src/api/deliverables', () => ({
  listDeliverables: vi.fn(),
}));

function makeDeliverable(overrides: Partial<DeliverableResponse> = {}): DeliverableResponse {
  return {
    id: '1', task_id: 'aaa', key: 'prd', deliverable_type: 'DOC',
    file_path: 'a.md', git_branch: 'temp/prd', category: 'docs',
    status: 'pending', reviewer: null, review_comment: null,
    reviewed_at: null, created_at: '2026-03-20T10:00:00Z',
    agent_id: 'analyst', phase: 'Discovery', project_slug: 'demo',
    ...overrides,
  };
}

describe('deliverableStore', () => {
  beforeEach(() => {
    useDeliverableStore.setState({
      deliverables: [],
      selectedId: null,
      filters: { phase: '', status: '', agent_id: '' },
      loading: false,
    });
  });

  it('initial state is empty', () => {
    const state = useDeliverableStore.getState();
    expect(state.deliverables).toEqual([]);
    expect(state.selectedId).toBeNull();
    expect(state.loading).toBe(false);
  });

  it('setFilters updates filters', () => {
    useDeliverableStore.getState().setFilters({ phase: 'Build', status: 'pending' });
    const state = useDeliverableStore.getState();
    expect(state.filters.phase).toBe('Build');
    expect(state.filters.status).toBe('pending');
    expect(state.filters.agent_id).toBe('');
  });

  it('setSelected updates selectedId', () => {
    useDeliverableStore.getState().setSelected('42');
    expect(useDeliverableStore.getState().selectedId).toBe('42');
  });

  it('setSelected clears with null', () => {
    useDeliverableStore.getState().setSelected('42');
    useDeliverableStore.getState().setSelected(null);
    expect(useDeliverableStore.getState().selectedId).toBeNull();
  });

  it('loadDeliverables populates list', async () => {
    const items = [makeDeliverable({ id: '1' }), makeDeliverable({ id: '2', key: 'specs' })];
    const { listDeliverables } = await import('../../src/api/deliverables');
    (listDeliverables as ReturnType<typeof vi.fn>).mockResolvedValueOnce(items);

    await useDeliverableStore.getState().loadDeliverables('demo');

    const state = useDeliverableStore.getState();
    expect(state.deliverables).toHaveLength(2);
    expect(state.deliverables[1].key).toBe('specs');
    expect(state.loading).toBe(false);
  });
});
