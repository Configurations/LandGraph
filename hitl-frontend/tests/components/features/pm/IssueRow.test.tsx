import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IssueRow } from '../../../../src/components/features/pm/IssueRow';
import type { IssueResponse } from '../../../../src/api/types';

const baseIssue: IssueResponse = {
  id: 'TEAM-001',
  project_id: '1',
  title: 'Setup CI pipeline',
  description: '',
  status: 'todo',
  priority: 1,
  assignee: 'alice@test.com',
  team_id: 'team1',
  tags: ['ci'],
  phase: 'build',
  created_by: 'bob@test.com',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  is_blocked: false,
  blocking_count: 0,
  blocked_by_count: 0,
};

describe('IssueRow', () => {
  it('renders ID in mono font', () => {
    render(<IssueRow issue={baseIssue} onClick={vi.fn()} />);
    const idEl = screen.getByText('TEAM-001');
    expect(idEl.className).toContain('font-mono');
  });

  it('shows priority badge with P1 red color', () => {
    const { container } = render(<IssueRow issue={{ ...baseIssue, priority: 1 }} onClick={vi.fn()} />);
    const bars = container.querySelectorAll('[title="P1"] div');
    const activeBar = bars[0];
    expect(activeBar?.className).toContain('bg-accent-red');
  });

  it('shows P4 gray color', () => {
    const { container } = render(<IssueRow issue={{ ...baseIssue, priority: 4 }} onClick={vi.fn()} />);
    const badge = container.querySelector('[title="P4"]');
    expect(badge).toBeTruthy();
  });

  it('shows status icon', () => {
    const { container } = render(<IssueRow issue={baseIssue} onClick={vi.fn()} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
  });

  it('shows lock icon when blocked', () => {
    const { container } = render(
      <IssueRow issue={{ ...baseIssue, is_blocked: true }} onClick={vi.fn()} />,
    );
    const redIcon = container.querySelector('.text-accent-red');
    expect(redIcon).toBeTruthy();
  });

  it('does not show lock icon when not blocked', () => {
    const { container } = render(
      <IssueRow issue={{ ...baseIssue, is_blocked: false }} onClick={vi.fn()} />,
    );
    const redIcons = container.querySelectorAll('.text-accent-red');
    expect(redIcons.length).toBe(0);
  });
});
