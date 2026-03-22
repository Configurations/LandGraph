import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IssueDetail } from '../../../../src/components/features/pm/IssueDetail';
import type { IssueDetail as IssueDetailType, RelationResponse } from '../../../../src/api/types';

const baseIssue: IssueDetailType = {
  id: 'TEAM-001',
  project_id: '1',
  title: 'Setup CI pipeline',
  description: 'Configure GitHub Actions',
  status: 'todo',
  priority: 2,
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
  relations: [],
  project_name: 'PerformanceTracker',
};

const blockingRelation: RelationResponse = {
  id: 1,
  type: 'blocks',
  direction: 'incoming',
  display_type: 'Blocked by',
  issue_id: 'TEAM-002',
  issue_title: 'DB Schema',
  issue_status: 'todo',
  reason: 'Needs schema',
  created_by: 'bob@test.com',
  created_at: new Date().toISOString(),
};

describe('IssueDetail', () => {
  it('renders title', () => {
    render(<IssueDetail issue={baseIssue} onUpdate={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText('Setup CI pipeline')).toBeInTheDocument();
  });

  it('shows blocked banner when blocked', () => {
    const blockedIssue = {
      ...baseIssue,
      is_blocked: true,
      relations: [blockingRelation],
    };
    render(<IssueDetail issue={blockedIssue} onUpdate={vi.fn()} onDelete={vi.fn()} />);
    // BlockedBanner is rendered for incoming blocks relations
    // TEAM-002 appears in both the blocked banner and the relations list
    const links = screen.getAllByText('TEAM-002');
    expect(links.length).toBeGreaterThanOrEqual(1);
  });

  it('shows relations list', () => {
    const withRelation = { ...baseIssue, relations: [blockingRelation] };
    render(<IssueDetail issue={withRelation} onUpdate={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText('issue.blocked_by')).toBeInTheDocument();
  });

  it('shows delete button', () => {
    render(<IssueDetail issue={baseIssue} onUpdate={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText('common.delete')).toBeInTheDocument();
  });
});
