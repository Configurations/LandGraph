import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProjectTabs } from '../../../../src/components/features/project/ProjectTabs';

const TAB_LABELS = [
  'project_detail.tab_issues',
  'project_detail.tab_deliverables',
  'project_detail.tab_workflow',
  'project_detail.tab_activity',
  'project_detail.tab_team',
  'project_detail.tab_dependencies',
];

describe('ProjectTabs', () => {
  it('renders all 6 tab labels', () => {
    render(<ProjectTabs activeTab="issues" onTabChange={vi.fn()} />);
    for (const label of TAB_LABELS) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it('highlights the active tab with accent color', () => {
    const { container } = render(
      <ProjectTabs activeTab="workflow" onTabChange={vi.fn()} />,
    );
    const buttons = container.querySelectorAll('button');
    const workflowBtn = buttons[2]; // 3rd tab
    expect(workflowBtn.className).toContain('border-accent-blue');
  });

  it('calls onTabChange on click', () => {
    const onChange = vi.fn();
    render(<ProjectTabs activeTab="issues" onTabChange={onChange} />);
    fireEvent.click(screen.getByText('project_detail.tab_team'));
    expect(onChange).toHaveBeenCalledWith('team');
  });
});
