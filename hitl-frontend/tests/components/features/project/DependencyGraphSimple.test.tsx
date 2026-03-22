import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { DependencyGraphSimple } from '../../../../src/components/features/project/DependencyGraphSimple';
import type { IssueResponse } from '../../../../src/api/types';

// Override useNavigate for this test
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
});

const issues: IssueResponse[] = [
  {
    id: 'TEAM-001', project_id: '1', title: 'Auth module', description: '',
    status: 'todo', priority: 1, assignee: 'alice', team_id: 'team1',
    tags: [], phase: 'build', created_by: 'bob', is_blocked: false,
    blocking_count: 1, blocked_by_count: 0,
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
  {
    id: 'TEAM-002', project_id: '1', title: 'Dashboard', description: '',
    status: 'backlog', priority: 2, assignee: 'bob', team_id: 'team1',
    tags: [], phase: 'build', created_by: 'bob', is_blocked: true,
    blocking_count: 0, blocked_by_count: 1,
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
];

const relations = [
  { sourceId: 'TEAM-001', targetId: 'TEAM-002', type: 'blocks' as const },
];

describe('DependencyGraphSimple', () => {
  it('renders SVG element', () => {
    const { container } = render(
      <DependencyGraphSimple issues={issues} relations={relations} />,
    );
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
  });

  it('renders issue nodes with IDs', () => {
    const { container } = render(
      <DependencyGraphSimple issues={issues} relations={relations} />,
    );
    const texts = container.querySelectorAll('text');
    const ids = Array.from(texts).map((t) => t.textContent);
    expect(ids).toContain('TEAM-001');
    expect(ids).toContain('TEAM-002');
  });

  it('renders edges between related issues', () => {
    const { container } = render(
      <DependencyGraphSimple issues={issues} relations={relations} />,
    );
    const lines = container.querySelectorAll('line');
    expect(lines.length).toBe(1);
    // Blocks relation uses red stroke
    expect(lines[0].getAttribute('stroke')).toBe('#ef4444');
  });

  it('shows no-dependencies message when issues list is empty', () => {
    const { container } = render(
      <DependencyGraphSimple issues={[]} relations={[]} />,
    );
    expect(container.querySelector('svg')).toBeNull();
    expect(container.textContent).toContain('project_detail.no_dependencies');
  });
});
