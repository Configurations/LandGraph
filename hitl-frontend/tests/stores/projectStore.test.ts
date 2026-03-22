import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useProjectStore } from '../../src/stores/projectStore';

// Mock the projects API
vi.mock('../../src/api/projects', () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  getProject: vi.fn(),
  checkSlug: vi.fn(),
  testGitConnection: vi.fn(),
  initGit: vi.fn(),
  getGitStatus: vi.fn(),
}));

describe('projectStore', () => {
  beforeEach(() => {
    useProjectStore.setState({
      projects: [],
      activeSlug: null,
      wizardStep: 0,
      wizardData: { name: '', slug: '', language: 'fr', teamId: '', gitConfig: null },
      loading: false,
    });
  });

  it('initial state has empty projects', () => {
    const state = useProjectStore.getState();
    expect(state.projects).toEqual([]);
    expect(state.activeSlug).toBeNull();
    expect(state.wizardStep).toBe(0);
    expect(state.loading).toBe(false);
  });

  it('setWizardStep updates step', () => {
    useProjectStore.getState().setWizardStep(2);
    expect(useProjectStore.getState().wizardStep).toBe(2);
  });

  it('updateWizardData merges data', () => {
    useProjectStore.getState().updateWizardData({ name: 'Hello' });
    const wd = useProjectStore.getState().wizardData;
    expect(wd.name).toBe('Hello');
    expect(wd.slug).toBe(''); // unchanged
    expect(wd.language).toBe('fr'); // unchanged
  });

  it('updateWizardData handles multiple fields', () => {
    useProjectStore.getState().updateWizardData({ name: 'X', slug: 'x', teamId: 't2' });
    const wd = useProjectStore.getState().wizardData;
    expect(wd.name).toBe('X');
    expect(wd.slug).toBe('x');
    expect(wd.teamId).toBe('t2');
  });

  it('resetWizard clears state', () => {
    useProjectStore.getState().setWizardStep(3);
    useProjectStore.getState().updateWizardData({ name: 'foo', slug: 'foo' });
    useProjectStore.getState().resetWizard();

    const state = useProjectStore.getState();
    expect(state.wizardStep).toBe(0);
    expect(state.wizardData.name).toBe('');
    expect(state.wizardData.slug).toBe('');
    expect(state.wizardData.gitConfig).toBeNull();
  });

  it('setActiveSlug updates active slug', () => {
    useProjectStore.getState().setActiveSlug('my-proj');
    expect(useProjectStore.getState().activeSlug).toBe('my-proj');
  });
});
