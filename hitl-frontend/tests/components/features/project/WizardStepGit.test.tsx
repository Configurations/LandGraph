import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WizardStepGit } from '../../../../src/components/features/project/WizardStepGit';
import { useProjectStore } from '../../../../src/stores/projectStore';

// Mock the projects API
vi.mock('../../../../src/api/projects', () => ({
  testGitConnection: vi.fn(),
}));

describe('WizardStepGit', () => {
  beforeEach(() => {
    useProjectStore.setState({
      wizardData: { name: 'Test', slug: 'test', language: 'fr', teamId: 'team1', gitConfig: null },
      wizardStep: 1,
    });
  });

  it('renders service selector', () => {
    render(<WizardStepGit />);
    expect(screen.getByText('git.service')).toBeInTheDocument();
    // The select should contain GitHub option
    const select = screen.getAllByRole('combobox')[0];
    expect(select).toBeInTheDocument();
  });

  it('auto-fills URL when GitHub selected', () => {
    render(<WizardStepGit />);
    const select = screen.getAllByRole('combobox')[0];
    fireEvent.change(select, { target: { value: 'github' } });

    // URL input should now have github URL
    const urlInput = screen.getAllByRole('textbox')[0];
    expect(urlInput).toHaveValue('https://github.com');
  });

  it('shows login and token inputs', () => {
    render(<WizardStepGit />);
    expect(screen.getByText('git.login')).toBeInTheDocument();
    expect(screen.getByText('git.token')).toBeInTheDocument();
  });

  it('test connection button calls API', async () => {
    const api = await import('../../../../src/api/projects');
    (api.testGitConnection as ReturnType<typeof vi.fn>).mockResolvedValue({
      connected: true,
      repo_exists: true,
    });

    render(<WizardStepGit />);

    // Fill in required fields
    const select = screen.getAllByRole('combobox')[0];
    fireEvent.change(select, { target: { value: 'github' } });

    const textInputs = screen.getAllByRole('textbox');
    fireEvent.change(textInputs[1], { target: { value: 'myuser' } }); // login
    fireEvent.change(textInputs[2], { target: { value: 'myuser/repo' } }); // repo_name

    // Click test button
    const testBtn = screen.getByRole('button', { name: /git\.test_connection/i });
    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(api.testGitConnection).toHaveBeenCalled();
    });
  });

  it('shows error message on connection failure', async () => {
    const api = await import('../../../../src/api/projects');
    (api.testGitConnection as ReturnType<typeof vi.fn>).mockResolvedValue({
      connected: false,
      repo_exists: false,
      error: 'auth_failed',
    });

    render(<WizardStepGit />);

    const testBtn = screen.getByRole('button', { name: /git\.test_connection/i });
    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(screen.getByText('auth_failed')).toBeInTheDocument();
    });
  });
});
