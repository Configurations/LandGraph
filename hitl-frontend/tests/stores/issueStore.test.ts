import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useIssueStore } from '../../src/stores/issueStore';

// Mock the issues API
vi.mock('../../src/api/issues', () => ({
  listIssues: vi.fn(),
  createIssue: vi.fn(),
  updateIssue: vi.fn(),
  deleteIssue: vi.fn(),
  getIssue: vi.fn(),
  searchIssues: vi.fn(),
  bulkCreateIssues: vi.fn(),
}));

describe('issueStore', () => {
  beforeEach(() => {
    useIssueStore.setState({
      issues: [],
      selectedId: null,
      filters: { teamId: '', projectId: '', status: '', assignee: '' },
      groupBy: 'status',
      loading: false,
    });
  });

  it('initial state has empty issues', () => {
    const state = useIssueStore.getState();
    expect(state.issues).toEqual([]);
    expect(state.selectedId).toBeNull();
    expect(state.groupBy).toBe('status');
    expect(state.loading).toBe(false);
  });

  it('setFilters updates filter values', () => {
    useIssueStore.getState().setFilters({ teamId: 'team1', status: 'todo' });
    const { filters } = useIssueStore.getState();
    expect(filters.teamId).toBe('team1');
    expect(filters.status).toBe('todo');
    // Unchanged fields preserved
    expect(filters.assignee).toBe('');
    expect(filters.projectId).toBe('');
  });

  it('setGroupBy updates groupBy', () => {
    useIssueStore.getState().setGroupBy('assignee');
    expect(useIssueStore.getState().groupBy).toBe('assignee');
  });

  it('setSelected updates selectedId', () => {
    useIssueStore.getState().setSelected('TEAM-001');
    expect(useIssueStore.getState().selectedId).toBe('TEAM-001');
  });

  it('setSelected to null clears selection', () => {
    useIssueStore.getState().setSelected('TEAM-001');
    useIssueStore.getState().setSelected(null);
    expect(useIssueStore.getState().selectedId).toBeNull();
  });
});
