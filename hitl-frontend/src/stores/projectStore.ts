import { create } from 'zustand';
import * as projectsApi from '../api/projects';
import type { GitTestPayload, ProjectResponse } from '../api/types';

interface WizardData {
  name: string;
  slug: string;
  language: string;
  teamId: string;
  gitConfig: GitTestPayload | null;
}

const defaultWizardData: WizardData = {
  name: '',
  slug: '',
  language: 'fr',
  teamId: '',
  gitConfig: null,
};

interface ProjectState {
  projects: ProjectResponse[];
  activeSlug: string | null;
  wizardStep: number;
  wizardData: WizardData;
  loading: boolean;
  loadProjects: () => Promise<void>;
  setActiveSlug: (slug: string | null) => void;
  setWizardStep: (step: number) => void;
  updateWizardData: (partial: Partial<WizardData>) => void;
  resetWizard: () => void;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  activeSlug: null,
  wizardStep: 0,
  wizardData: { ...defaultWizardData },
  loading: false,

  loadProjects: async () => {
    set({ loading: true });
    try {
      const projects = await projectsApi.listProjects();
      set({ projects, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  setActiveSlug: (slug) => set({ activeSlug: slug }),

  setWizardStep: (step) => set({ wizardStep: step }),

  updateWizardData: (partial) =>
    set({ wizardData: { ...get().wizardData, ...partial } }),

  resetWizard: () =>
    set({ wizardStep: 0, wizardData: { ...defaultWizardData } }),
}));
