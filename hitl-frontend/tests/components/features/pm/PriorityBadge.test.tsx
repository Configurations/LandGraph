import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { PriorityBadge } from '../../../../src/components/features/pm/PriorityBadge';
import type { IssuePriority } from '../../../../src/api/types';

describe('PriorityBadge', () => {
  it('renders 4 bars for P1', () => {
    const { container } = render(<PriorityBadge priority={1} />);
    const bars = container.querySelectorAll('[title="P1"] div');
    expect(bars.length).toBe(4);
    // P1 = 4 active bars (5 - 1), color red
    expect(bars[0].className).toContain('bg-accent-red');
  });

  it('renders 4 bars for P2 (orange)', () => {
    const { container } = render(<PriorityBadge priority={2} />);
    const bars = container.querySelectorAll('[title="P2"] div');
    expect(bars.length).toBe(4);
    expect(bars[0].className).toContain('bg-accent-orange');
  });

  it('renders 4 bars for P3 (yellow)', () => {
    const { container } = render(<PriorityBadge priority={3} />);
    const bars = container.querySelectorAll('[title="P3"] div');
    expect(bars.length).toBe(4);
    expect(bars[0].className).toContain('bg-accent-yellow');
  });

  it('renders 4 bars for P4 (gray)', () => {
    const { container } = render(<PriorityBadge priority={4} />);
    const bars = container.querySelectorAll('[title="P4"] div');
    expect(bars.length).toBe(4);
    // P4 = 1 active bar, first bar is active (quaternary)
    expect(bars[0].className).toContain('bg-content-quaternary');
  });
});
