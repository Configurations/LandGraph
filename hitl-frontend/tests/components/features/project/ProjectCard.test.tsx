import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProjectCard } from '../../../../src/components/features/project/ProjectCard';
import type { ProjectResponse } from '../../../../src/api/types';

// Mock GitStatusBadge to avoid dependency complexity
vi.mock('../../../../src/components/features/project/GitStatusBadge', () => ({
  GitStatusBadge: ({ connected }: { connected: boolean }) => (
    <span data-testid="git-badge">{connected ? 'connected' : 'disconnected'}</span>
  ),
}));

const mockProject: ProjectResponse = {
  id: '1',
  name: 'Performance Tracker',
  slug: 'performance-tracker',
  team_id: 'team1',
  language: 'fr',
  git_connected: true,
  git_repo_exists: true,
  created_at: new Date(Date.now() - 3600_000).toISOString(), // 1 hour ago
};

describe('ProjectCard', () => {
  it('renders project name', () => {
    render(<ProjectCard project={mockProject} />);
    expect(screen.getByText('Performance Tracker')).toBeInTheDocument();
  });

  it('shows slug in mono font', () => {
    render(<ProjectCard project={mockProject} />);
    const slugEl = screen.getByText('performance-tracker');
    expect(slugEl).toBeInTheDocument();
    expect(slugEl.className).toContain('font-mono');
  });

  it('displays team badge', () => {
    render(<ProjectCard project={mockProject} />);
    expect(screen.getByText('team1')).toBeInTheDocument();
  });

  it('shows relative time', () => {
    render(<ProjectCard project={mockProject} />);
    // The t() mock returns the key, so we check for a time key
    expect(screen.getByText(/time\./)).toBeInTheDocument();
  });
});
