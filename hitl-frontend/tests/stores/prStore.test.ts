import { describe, it, expect, vi, beforeEach } from 'vitest';
import { usePRStore } from '../../src/stores/prStore';

// Mock the prs API
vi.mock('../../src/api/prs', () => ({
  listPRs: vi.fn(),
  createPR: vi.fn(),
  getPR: vi.fn(),
  updatePRStatus: vi.fn(),
  mergePR: vi.fn(),
}));

describe('prStore', () => {
  beforeEach(() => {
    usePRStore.setState({
      prs: [],
      selectedId: null,
      statusFilter: '',
      loading: false,
    });
  });

  it('initial state has empty prs', () => {
    const state = usePRStore.getState();
    expect(state.prs).toEqual([]);
    expect(state.selectedId).toBeNull();
    expect(state.statusFilter).toBe('');
    expect(state.loading).toBe(false);
  });

  it('loadPRs populates the list', async () => {
    const { listPRs } = await import('../../src/api/prs');
    const mockPRs = [
      { id: 'PR-001', title: 'Test PR', status: 'open' },
    ];
    (listPRs as ReturnType<typeof vi.fn>).mockResolvedValue(mockPRs);

    await usePRStore.getState().loadPRs();
    const state = usePRStore.getState();
    expect(state.prs).toEqual(mockPRs);
    expect(state.loading).toBe(false);
  });

  it('setStatusFilter updates the filter', () => {
    usePRStore.getState().setStatusFilter('approved');
    expect(usePRStore.getState().statusFilter).toBe('approved');
  });

  it('setStatusFilter to empty clears filter', () => {
    usePRStore.getState().setStatusFilter('merged');
    usePRStore.getState().setStatusFilter('');
    expect(usePRStore.getState().statusFilter).toBe('');
  });

  it('setSelected updates selectedId', () => {
    usePRStore.getState().setSelected('PR-001');
    expect(usePRStore.getState().selectedId).toBe('PR-001');
  });

  it('setSelected to null clears selection', () => {
    usePRStore.getState().setSelected('PR-001');
    usePRStore.getState().setSelected(null);
    expect(usePRStore.getState().selectedId).toBeNull();
  });
});
