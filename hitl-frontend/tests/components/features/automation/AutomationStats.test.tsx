import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AutomationStats } from '../../../../src/components/features/automation/AutomationStats';
import type { AutomationStats as AutomationStatsType } from '../../../../src/api/types';

const stats: AutomationStatsType = {
  total_decisions: 100,
  auto_approved: 60,
  manual_reviewed: 30,
  rejected: 10,
};

describe('AutomationStats', () => {
  it('renders 3 segment labels', () => {
    render(<AutomationStats stats={stats} />);
    expect(screen.getByText(/automation\.auto_approved/)).toBeTruthy();
    expect(screen.getByText(/automation\.manual_reviewed/)).toBeTruthy();
    expect(screen.getByText(/automation\.rejected/)).toBeTruthy();
  });

  it('shows percentages in labels', () => {
    render(<AutomationStats stats={stats} />);
    expect(screen.getByText(/60%/)).toBeTruthy();
    expect(screen.getByText(/30%/)).toBeTruthy();
    expect(screen.getByText(/10%/)).toBeTruthy();
  });

  it('renders colored bar segments', () => {
    const { container } = render(<AutomationStats stats={stats} />);
    const segments = container.querySelectorAll('.bg-accent-green, .bg-accent-blue, .bg-accent-red');
    // 3 in bar + 3 in legend = 6
    expect(segments.length).toBe(6);
  });
});
