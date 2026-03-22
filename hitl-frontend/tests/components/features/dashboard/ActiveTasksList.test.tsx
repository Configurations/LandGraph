import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActiveTasksList } from '../../../../src/components/features/dashboard/ActiveTasksList';
import type { ActiveTask } from '../../../../src/api/types';

function makeTask(overrides: Partial<ActiveTask> = {}): ActiveTask {
  return {
    task_id: '1', agent_id: 'lead_dev', team_id: 'team1',
    project_slug: 'demo', phase: 'Build', status: 'running',
    cost_usd: 0.0042, started_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('ActiveTasksList', () => {
  it('renders task cards', () => {
    const tasks = [
      makeTask({ task_id: '1', agent_id: 'lead_dev' }),
      makeTask({ task_id: '2', agent_id: 'qa_engineer' }),
    ];
    render(<ActiveTasksList tasks={tasks} />);
    expect(screen.getByText('lead_dev')).toBeInTheDocument();
    expect(screen.getByText('qa_engineer')).toBeInTheDocument();
  });

  it('shows empty state when no tasks', () => {
    render(<ActiveTasksList tasks={[]} />);
    expect(screen.getByText('dashboard.no_active_tasks')).toBeInTheDocument();
  });

  it('shows agent and phase', () => {
    render(<ActiveTasksList tasks={[makeTask({ phase: 'Discovery' })]} />);
    expect(screen.getByText('Discovery')).toBeInTheDocument();
  });
});
