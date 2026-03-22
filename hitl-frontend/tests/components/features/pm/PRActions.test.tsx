import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PRActions } from '../../../../src/components/features/pm/PRActions';

describe('PRActions', () => {
  const handlers = {
    onApprove: vi.fn(),
    onRequestChanges: vi.fn(),
    onMerge: vi.fn(),
  };

  it('shows approve and request-changes when status is open', () => {
    render(<PRActions status="open" {...handlers} />);
    expect(screen.getByText('pr.approve')).toBeTruthy();
    expect(screen.getByText('pr.request_changes')).toBeTruthy();
  });

  it('shows approve and request-changes when changes_requested', () => {
    render(<PRActions status="changes_requested" {...handlers} />);
    expect(screen.getByText('pr.approve')).toBeTruthy();
    expect(screen.getByText('pr.request_changes')).toBeTruthy();
  });

  it('shows merge button when approved', () => {
    render(<PRActions status="approved" {...handlers} />);
    expect(screen.getByText('pr.merge')).toBeTruthy();
  });

  it('hides merge button when not approved', () => {
    render(<PRActions status="open" {...handlers} />);
    expect(screen.queryByText('pr.merge')).toBeNull();
  });

  it('hides review buttons when merged', () => {
    render(<PRActions status="merged" {...handlers} />);
    expect(screen.queryByText('pr.approve')).toBeNull();
    expect(screen.queryByText('pr.merge')).toBeNull();
  });
});
