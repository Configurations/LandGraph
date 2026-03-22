import { create } from 'zustand';
import * as issuesApi from '../api/issues';
import type { IssueGroupBy, IssueListParams, IssueResponse, IssueStatus } from '../api/types';

interface IssueFilters {
  teamId: string;
  projectId: string;
  status: IssueStatus | '';
  assignee: string;
}

interface IssueState {
  issues: IssueResponse[];
  selectedId: string | null;
  filters: IssueFilters;
  groupBy: IssueGroupBy;
  loading: boolean;
  loadIssues: () => Promise<void>;
  setSelected: (id: string | null) => void;
  setFilters: (partial: Partial<IssueFilters>) => void;
  setGroupBy: (groupBy: IssueGroupBy) => void;
}

export const useIssueStore = create<IssueState>((set, get) => ({
  issues: [],
  selectedId: null,
  filters: { teamId: '', projectId: '', status: '', assignee: '' },
  groupBy: 'status',
  loading: false,

  loadIssues: async () => {
    set({ loading: true });
    try {
      const { teamId, projectId, status, assignee } = get().filters;
      const params: IssueListParams = {};
      if (teamId) params.team_id = teamId;
      if (projectId) params.project_id = projectId;
      if (status) params.status = status;
      if (assignee) params.assignee = assignee;
      const issues = await issuesApi.listIssues(params);
      set({ issues, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  setSelected: (id) => set({ selectedId: id }),

  setFilters: (partial) =>
    set((state) => ({ filters: { ...state.filters, ...partial } })),

  setGroupBy: (groupBy) => set({ groupBy }),
}));
