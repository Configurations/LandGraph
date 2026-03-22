import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { IssueStatusIcon } from '../../../../src/components/features/pm/IssueStatusIcon';
import type { IssueStatus } from '../../../../src/api/types';

describe('IssueStatusIcon', () => {
  const statuses: IssueStatus[] = ['backlog', 'todo', 'in-progress', 'in-review', 'done'];

  it('renders an SVG for each status', () => {
    for (const status of statuses) {
      const { container } = render(<IssueStatusIcon status={status} />);
      const svg = container.querySelector('svg');
      expect(svg).toBeTruthy();
    }
  });

  it('backlog uses dashed circle (strokeDasharray)', () => {
    const { container } = render(<IssueStatusIcon status="backlog" />);
    const circle = container.querySelector('circle');
    expect(circle?.getAttribute('stroke-dasharray')).toBe('2 2');
  });

  it('todo uses plain circle', () => {
    const { container } = render(<IssueStatusIcon status="todo" />);
    const circle = container.querySelector('circle');
    expect(circle).toBeTruthy();
    expect(circle?.getAttribute('stroke-dasharray')).toBeNull();
  });

  it('in-progress has a filled half', () => {
    const { container } = render(<IssueStatusIcon status="in-progress" />);
    const path = container.querySelector('path');
    expect(path?.getAttribute('fill')).toBe('currentColor');
  });

  it('done has a checkmark path', () => {
    const { container } = render(<IssueStatusIcon status="done" />);
    const paths = container.querySelectorAll('path');
    const checkmark = Array.from(paths).find((p) => p.getAttribute('stroke') === 'white');
    expect(checkmark).toBeTruthy();
  });
});
