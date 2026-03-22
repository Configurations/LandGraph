import { create } from 'zustand';
import * as teamsApi from '../api/teams';
import type { TeamResponse } from '../api/types';

interface TeamState {
  teams: TeamResponse[];
  activeTeamId: string | null;
  loading: boolean;
  setActiveTeam: (id: string) => void;
  loadTeams: () => Promise<void>;
}

const ACTIVE_TEAM_KEY = 'hitl_active_team';

export const useTeamStore = create<TeamState>((set) => ({
  teams: [],
  activeTeamId: localStorage.getItem(ACTIVE_TEAM_KEY),
  loading: false,

  setActiveTeam: (id) => {
    localStorage.setItem(ACTIVE_TEAM_KEY, id);
    set({ activeTeamId: id });
  },

  loadTeams: async () => {
    set({ loading: true });
    try {
      const teams = await teamsApi.listTeams();
      set((state) => {
        const validId = state.activeTeamId && teams.some((t) => t.id === state.activeTeamId)
          ? state.activeTeamId
          : teams[0]?.id ?? null;
        if (validId) {
          localStorage.setItem(ACTIVE_TEAM_KEY, validId);
        }
        return { teams, activeTeamId: validId, loading: false };
      });
    } catch {
      set({ loading: false });
    }
  },
}));
