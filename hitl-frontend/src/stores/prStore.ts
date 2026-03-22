import { create } from 'zustand';
import * as prsApi from '../api/prs';
import type { PRListParams, PRResponse, PRStatus } from '../api/types';

interface PRState {
  prs: PRResponse[];
  selectedId: string | null;
  statusFilter: PRStatus | '';
  loading: boolean;
  loadPRs: (projectId?: string) => Promise<void>;
  setSelected: (id: string | null) => void;
  setStatusFilter: (status: PRStatus | '') => void;
}

export const usePRStore = create<PRState>((set, get) => ({
  prs: [],
  selectedId: null,
  statusFilter: '',
  loading: false,

  loadPRs: async (projectId?: string) => {
    set({ loading: true });
    try {
      const params: PRListParams = {};
      if (projectId) params.project_id = projectId;
      const statusFilter = get().statusFilter;
      if (statusFilter) params.status = statusFilter;
      const prs = await prsApi.listPRs(params);
      set({ prs, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  setSelected: (id) => set({ selectedId: id }),

  setStatusFilter: (status) => set({ statusFilter: status }),
}));
