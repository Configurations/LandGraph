import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WizardStepSetup } from '../../../../src/components/features/project/WizardStepSetup';
import { useProjectStore } from '../../../../src/stores/projectStore';
import { useTeamStore } from '../../../../src/stores/teamStore';

// Mock the projects API
vi.mock('../../../../src/api/projects', () => ({
  checkSlug: vi.fn(),
}));

describe('WizardStepSetup', () => {
  beforeEach(() => {
    useProjectStore.setState({
      wizardData: { name: '', slug: '', language: 'fr', teamId: 'team1', gitConfig: null },
      wizardStep: 0,
    });
    useTeamStore.setState({
      teams: [{ id: 'team1', name: 'Team 1', directory: 'Team1' }],
      activeTeamId: 'team1',
    });
  });

  it('renders name and slug inputs', () => {
    render(<WizardStepSetup />);
    expect(screen.getByText('project.name')).toBeInTheDocument();
    expect(screen.getByText('project.slug')).toBeInTheDocument();
  });

  it('auto-generates slug from name', () => {
    render(<WizardStepSetup />);
    const nameInput = screen.getAllByRole('textbox')[0];
    fireEvent.change(nameInput, { target: { value: 'My Cool Project' } });

    const state = useProjectStore.getState();
    expect(state.wizardData.name).toBe('My Cool Project');
    expect(state.wizardData.slug).toBe('my-cool-project');
  });

  it('shows available indicator when slug is free', async () => {
    const api = await import('../../../../src/api/projects');
    (api.checkSlug as ReturnType<typeof vi.fn>).mockResolvedValue({ available: true });

    useProjectStore.setState({
      wizardData: { name: 'Test', slug: 'test', language: 'fr', teamId: 'team1', gitConfig: null },
    });

    render(<WizardStepSetup />);

    await waitFor(() => {
      expect(screen.getByText('project.slug_available')).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('shows exists indicator when slug is taken', async () => {
    const api = await import('../../../../src/api/projects');
    (api.checkSlug as ReturnType<typeof vi.fn>).mockResolvedValue({ available: false });

    useProjectStore.setState({
      wizardData: { name: 'Taken', slug: 'taken', language: 'fr', teamId: 'team1', gitConfig: null },
    });

    render(<WizardStepSetup />);

    await waitFor(() => {
      expect(screen.getByText('project.slug_exists')).toBeInTheDocument();
    }, { timeout: 2000 });
  });
});
