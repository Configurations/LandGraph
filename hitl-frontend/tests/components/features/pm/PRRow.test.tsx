import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PRRow } from '../../../../src/components/features/pm/PRRow';
import type { PRResponse } from '../../../../src/api/types';

const basePR: PRResponse = {
  id: 'PR-001',
  project_id: '1',
  title: 'Add login page',
  description: '',
  branch: 'feat/login',
  target_branch: 'main',
  status: 'open',
  author: 'alice@test.com',
  issue_id: 'TEAM-001',
  files_changed: 5,
  additions: 120,
  deletions: 30,
  remote_url: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

describe('PRRow', () => {
  it('renders title', () => {
    render(<PRRow pr={basePR} onClick={vi.fn()} />);
    expect(screen.getByText('Add login page')).toBeTruthy();
  });

  it('renders branch ref via issue_id', () => {
    render(<PRRow pr={basePR} onClick={vi.fn()} />);
    expect(screen.getByText('TEAM-001')).toBeTruthy();
  });

  it('shows diff stats (additions and deletions)', () => {
    render(<PRRow pr={basePR} onClick={vi.fn()} />);
    expect(screen.getByText('+120')).toBeTruthy();
    expect(screen.getByText('-30')).toBeTruthy();
  });

  it('shows status badge for each status', () => {
    for (const status of ['draft', 'open', 'approved', 'merged'] as const) {
      const { unmount } = render(
        <PRRow pr={{ ...basePR, status }} onClick={vi.fn()} />,
      );
      expect(screen.getByText(`pr.status_${status}`)).toBeTruthy();
      unmount();
    }
  });
});
