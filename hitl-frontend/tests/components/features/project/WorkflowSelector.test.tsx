import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkflowSelector } from '../../../../src/components/features/project/WorkflowSelector';
import type { ProjectWorkflowResponse } from '../../../../src/api/types';

const workflows: ProjectWorkflowResponse[] = [
  { id: 'w1', project_id: '1', workflow_template_id: 't1', name: 'Discovery', type: 'discovery', mode: 'sequential', status: 'active', progress: 50, depends_on: [], created_at: '', updated_at: '' },
  { id: 'w2', project_id: '1', workflow_template_id: 't2', name: 'Design', type: 'design', mode: 'sequential', status: 'draft', progress: 0, depends_on: ['w1'], created_at: '', updated_at: '' },
];

describe('WorkflowSelector', () => {
  it('renders workflow tabs', () => {
    render(<WorkflowSelector workflows={workflows} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('Discovery')).toBeTruthy();
    expect(screen.getByText('Design')).toBeTruthy();
  });

  it('highlights active workflow', () => {
    const { container } = render(
      <WorkflowSelector workflows={workflows} selectedId="w1" onSelect={vi.fn()} />,
    );
    const selected = container.querySelector('.bg-accent-blue\\/10');
    expect(selected).toBeTruthy();
    expect(selected?.textContent).toContain('Discovery');
  });

  it('calls onSelect when clicking a tab', () => {
    const onSelect = vi.fn();
    render(<WorkflowSelector workflows={workflows} selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByText('Design'));
    expect(onSelect).toHaveBeenCalledWith('w2');
  });

  it('shows empty message when no workflows', () => {
    render(<WorkflowSelector workflows={[]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('multi_workflow.no_workflows')).toBeTruthy();
  });
});
