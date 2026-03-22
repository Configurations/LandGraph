import { create } from 'zustand';
import * as deliverablesApi from '../api/deliverables';
import type { DeliverableListParams, DeliverableResponse } from '../api/types';

interface DeliverableFilters {
  phase: string;
  status: string;
  agent_id: string;
}

interface DeliverableState {
  deliverables: DeliverableResponse[];
  selectedId: string | null;
  filters: DeliverableFilters;
  loading: boolean;
  loadDeliverables: (slug: string) => Promise<void>;
  setSelected: (id: string | null) => void;
  setFilters: (partial: Partial<DeliverableFilters>) => void;
}

export const useDeliverableStore = create<DeliverableState>((set, get) => ({
  deliverables: [],
  selectedId: null,
  filters: { phase: '', status: '', agent_id: '' },
  loading: false,

  loadDeliverables: async (slug: string) => {
    set({ loading: true });
    try {
      const { phase, status, agent_id } = get().filters;
      const params: DeliverableListParams = {};
      if (phase) params.phase = phase;
      if (status) params.status = status;
      if (agent_id) params.agent_id = agent_id;
      const deliverables = await deliverablesApi.listDeliverables(slug, params);
      set({ deliverables, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  setSelected: (id) => set({ selectedId: id }),

  setFilters: (partial) =>
    set((state) => ({ filters: { ...state.filters, ...partial } })),
}));
