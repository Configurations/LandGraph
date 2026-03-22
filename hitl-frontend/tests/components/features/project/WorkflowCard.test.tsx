import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkflowCard } from '../../../../src/components/features/project/WorkflowCard';
import type { ProjectWorkflowResponse } from '../../../../src/api/types';

const baseWorkflow: ProjectWorkflowResponse = {
  id: 'w1',
  project_id: '1',
  workflow_template_id: 't1',
  name: 'Discovery',
  type: 'discovery',
  mode: 'sequential',
  status: 'draft',
  progress: 30,
  depends_on: [],
  created_at: '',
  updated_at: '',
};

describe('WorkflowCard', () => {
  it('renders name, type, and status badges', () => {
    render(<WorkflowCard workflow={baseWorkflow} />);
    expect(screen.getByText('Discovery')).toBeTruthy();
    expect(screen.getByText('discovery')).toBeTruthy();
    expect(screen.getByText('multi_workflow.status_draft')).toBeTruthy();
  });

  it('shows activate button for draft status', () => {
    const onActivate = vi.fn();
    render(<WorkflowCard workflow={baseWorkflow} onActivate={onActivate} />);
    const btn = screen.getByText('multi_workflow.activate');
    expect(btn).toBeTruthy();
    fireEvent.click(btn);
    expect(onActivate).toHaveBeenCalledWith('w1');
  });

  it('shows pause and complete buttons for active status', () => {
    const onPause = vi.fn();
    const onComplete = vi.fn();
    render(
      <WorkflowCard
        workflow={{ ...baseWorkflow, status: 'active' }}
        onPause={onPause}
        onComplete={onComplete}
      />,
    );
    expect(screen.getByText('multi_workflow.pause')).toBeTruthy();
    expect(screen.getByText('multi_workflow.complete')).toBeTruthy();
    fireEvent.click(screen.getByText('multi_workflow.pause'));
    expect(onPause).toHaveBeenCalledWith('w1');
  });

  it('shows relaunch button for completed status', () => {
    const onRelaunch = vi.fn();
    render(
      <WorkflowCard
        workflow={{ ...baseWorkflow, status: 'completed' }}
        onRelaunch={onRelaunch}
      />,
    );
    fireEvent.click(screen.getByText('multi_workflow.relaunch'));
    expect(onRelaunch).toHaveBeenCalledWith('w1');
  });
});
