import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AutomationRuleList } from '../../../../src/components/features/automation/AutomationRuleList';
import type { AutomationRule } from '../../../../src/api/types';

const baseRule: AutomationRule = {
  id: 'r1',
  project_id: '1',
  workflow_type: 'discovery',
  deliverable_type: 'document',
  auto_approve: true,
  confidence_threshold: 0.8,
  min_history: 5,
  enabled: true,
  created_at: '',
  updated_at: '',
};

describe('AutomationRuleList', () => {
  const defaultProps = {
    rules: [baseRule, { ...baseRule, id: 'r2', enabled: false, auto_approve: false }],
    onToggle: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onAdd: vi.fn(),
  };

  it('renders rules table with badges', () => {
    render(<AutomationRuleList {...defaultProps} />);
    expect(screen.getAllByText('discovery').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('document').length).toBeGreaterThanOrEqual(1);
  });

  it('toggles rule on/off', () => {
    render(<AutomationRuleList {...defaultProps} />);
    const toggles = screen.getAllByLabelText('automation.toggle_rule');
    fireEvent.click(toggles[0]);
    expect(defaultProps.onToggle).toHaveBeenCalledWith('r1', false);
  });

  it('shows empty state when no rules', () => {
    render(<AutomationRuleList {...defaultProps} rules={[]} />);
    expect(screen.getByText('automation.no_rules')).toBeTruthy();
  });

  it('calls onAdd when clicking add button', () => {
    render(<AutomationRuleList {...defaultProps} />);
    fireEvent.click(screen.getByText('automation.add_rule'));
    expect(defaultProps.onAdd).toHaveBeenCalled();
  });
});
