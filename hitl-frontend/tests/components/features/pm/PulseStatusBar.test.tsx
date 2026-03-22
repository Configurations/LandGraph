import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { PulseStatusBar } from '../../../../src/components/features/pm/PulseStatusBar';
import type { IssueStatus } from '../../../../src/api/types';

const breakdown: Record<IssueStatus, number> = {
  backlog: 2,
  todo: 5,
  'in-progress': 3,
  'in-review': 1,
  done: 9,
};

describe('PulseStatusBar', () => {
  it('renders a segment for each non-zero status', () => {
    const { container } = render(<PulseStatusBar breakdown={breakdown} />);
    // The bar container has child divs with percentage widths
    const bar = container.querySelector('.flex.h-6');
    const segments = bar?.querySelectorAll('div[style]');
    // 5 non-zero statuses -> 5 segments
    expect(segments?.length).toBe(5);
  });

  it('renders proportional widths', () => {
    const { container } = render(<PulseStatusBar breakdown={breakdown} />);
    const bar = container.querySelector('.flex.h-6');
    const segments = bar?.querySelectorAll('div[style]');
    // Total = 20, done = 9 -> 45%
    const doneSegment = segments?.[4]; // done is last in order
    const style = doneSegment?.getAttribute('style') ?? '';
    expect(style).toContain('45%');
  });

  it('renders empty bar when total is zero', () => {
    const empty: Record<IssueStatus, number> = {
      backlog: 0, todo: 0, 'in-progress': 0, 'in-review': 0, done: 0,
    };
    const { container } = render(<PulseStatusBar breakdown={empty} />);
    const emptyBar = container.querySelector('.bg-surface-tertiary');
    expect(emptyBar).toBeTruthy();
  });
});
