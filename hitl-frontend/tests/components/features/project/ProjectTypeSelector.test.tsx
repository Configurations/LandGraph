import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ProjectTypeSelector } from '../../../../src/components/features/project/ProjectTypeSelector';

vi.mock('../../../../src/api/projectTypes', () => ({
  listProjectTypes: vi.fn().mockResolvedValue([
    {
      id: 'saas',
      name: 'SaaS Starter',
      description: 'Standard SaaS project',
      team_id: 'team1',
      workflows: [{ id: 'w1', name: 'Discovery', type: 'discovery', mode: 'sequential' }],
      created_at: '',
    },
  ]),
}));

describe('ProjectTypeSelector', () => {
  it('renders type cards after loading', async () => {
    render(<ProjectTypeSelector teamId="team1" selectedTypeId={null} onSelect={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('SaaS Starter')).toBeTruthy();
    });
  });

  it('highlights selected type', async () => {
    const { container } = render(
      <ProjectTypeSelector teamId="team1" selectedTypeId="saas" onSelect={vi.fn()} />,
    );
    await waitFor(() => {
      const selected = container.querySelector('.border-accent-blue');
      expect(selected).toBeTruthy();
    });
  });

  it('shows skip button', async () => {
    const onSelect = vi.fn();
    render(<ProjectTypeSelector teamId="team1" selectedTypeId={null} onSelect={onSelect} />);
    await waitFor(() => {
      const skipBtn = screen.getByText('project_type.skip');
      expect(skipBtn).toBeTruthy();
      fireEvent.click(skipBtn);
      expect(onSelect).toHaveBeenCalledWith(null);
    });
  });
});
