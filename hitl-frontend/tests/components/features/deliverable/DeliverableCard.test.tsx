import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DeliverableCard } from '../../../../src/components/features/deliverable/DeliverableCard';
import type { DeliverableResponse } from '../../../../src/api/types';

function makeDeliverable(overrides: Partial<DeliverableResponse> = {}): DeliverableResponse {
  return {
    id: '1', task_id: 'aaa', key: 'prd', deliverable_type: 'DOC',
    file_path: 'a.md', git_branch: 'temp/prd', category: 'documentation',
    status: 'pending', reviewer: null, review_comment: null,
    reviewed_at: null, created_at: new Date().toISOString(),
    agent_id: 'requirements_analyst', phase: 'Discovery', project_slug: 'demo',
    ...overrides,
  };
}

describe('DeliverableCard', () => {
  it('renders key and agent name', () => {
    render(<DeliverableCard deliverable={makeDeliverable()} onClick={vi.fn()} />);
    expect(screen.getByText('prd')).toBeInTheDocument();
  });

  it('shows approved badge (green)', () => {
    const { container } = render(
      <DeliverableCard deliverable={makeDeliverable({ status: 'approved' })} onClick={vi.fn()} />,
    );
    const badge = container.querySelector('[class*="green"]');
    expect(badge).toBeTruthy();
  });

  it('shows pending badge (orange)', () => {
    const { container } = render(
      <DeliverableCard deliverable={makeDeliverable({ status: 'pending' })} onClick={vi.fn()} />,
    );
    const badge = container.querySelector('[class*="orange"]');
    expect(badge).toBeTruthy();
  });

  it('shows rejected badge (red)', () => {
    const { container } = render(
      <DeliverableCard deliverable={makeDeliverable({ status: 'rejected' })} onClick={vi.fn()} />,
    );
    const badge = container.querySelector('[class*="red"]');
    expect(badge).toBeTruthy();
  });

  it('shows type badge (DOC)', () => {
    render(<DeliverableCard deliverable={makeDeliverable()} onClick={vi.fn()} />);
    expect(screen.getByText('DOC')).toBeInTheDocument();
  });

  it('shows type badge (CODE)', () => {
    render(<DeliverableCard deliverable={makeDeliverable({ deliverable_type: 'CODE' })} onClick={vi.fn()} />);
    expect(screen.getByText('CODE')).toBeInTheDocument();
  });
});
