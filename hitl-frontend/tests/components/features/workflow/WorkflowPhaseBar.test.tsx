import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkflowPhaseBar } from '../../../../src/components/features/workflow/WorkflowPhaseBar';
import type { PhaseStatus } from '../../../../src/api/types';

const phases: PhaseStatus[] = [
  { id: 'discovery', name: 'Discovery', status: 'completed', agents: [], deliverables: [] },
  { id: 'design', name: 'Design', status: 'active', agents: [], deliverables: [] },
  { id: 'build', name: 'Build', status: 'pending', agents: [], deliverables: [] },
];

describe('WorkflowPhaseBar', () => {
  it('renders a circle button for each phase', () => {
    const { container } = render(
      <WorkflowPhaseBar phases={phases} selectedPhaseId={null} onSelectPhase={vi.fn()} />,
    );
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBe(3);
  });

  it('numbers phases starting from 1', () => {
    render(
      <WorkflowPhaseBar phases={phases} selectedPhaseId={null} onSelectPhase={vi.fn()} />,
    );
    expect(screen.getByText('1')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
  });

  it('applies completed color to finished phases', () => {
    const { container } = render(
      <WorkflowPhaseBar phases={phases} selectedPhaseId={null} onSelectPhase={vi.fn()} />,
    );
    const buttons = container.querySelectorAll('button');
    expect(buttons[0].className).toContain('bg-accent-green');
  });

  it('applies active color to current phase', () => {
    const { container } = render(
      <WorkflowPhaseBar phases={phases} selectedPhaseId={null} onSelectPhase={vi.fn()} />,
    );
    const buttons = container.querySelectorAll('button');
    expect(buttons[1].className).toContain('bg-accent-blue');
  });

  it('calls onSelectPhase when clicking a phase', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <WorkflowPhaseBar phases={phases} selectedPhaseId={null} onSelectPhase={onSelect} />,
    );
    const buttons = container.querySelectorAll('button');
    fireEvent.click(buttons[1]);
    expect(onSelect).toHaveBeenCalledWith('design');
  });
});
