import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DeliverableActions } from '../../../../src/components/features/deliverable/DeliverableActions';

describe('DeliverableActions', () => {
  const defaultProps = {
    onApprove: vi.fn(),
    onReject: vi.fn(),
    onRemark: vi.fn(),
    onEdit: vi.fn(),
  };

  it('shows approve/reject buttons when pending', () => {
    render(<DeliverableActions status="pending" {...defaultProps} />);
    expect(screen.getByText('deliverable.approve')).toBeInTheDocument();
    expect(screen.getByText('deliverable.reject')).toBeInTheDocument();
  });

  it('hides approve/reject when not pending', () => {
    render(<DeliverableActions status="approved" {...defaultProps} />);
    expect(screen.queryByText('deliverable.approve')).not.toBeInTheDocument();
    expect(screen.queryByText('deliverable.reject')).not.toBeInTheDocument();
  });

  it('calls onApprove on click', () => {
    const onApprove = vi.fn();
    render(<DeliverableActions status="pending" {...defaultProps} onApprove={onApprove} />);
    fireEvent.click(screen.getByText('deliverable.approve'));
    expect(onApprove).toHaveBeenCalledOnce();
  });

  it('calls onReject on click', () => {
    const onReject = vi.fn();
    render(<DeliverableActions status="pending" {...defaultProps} onReject={onReject} />);
    fireEvent.click(screen.getByText('deliverable.reject'));
    expect(onReject).toHaveBeenCalledOnce();
  });

  it('shows remark button always', () => {
    render(<DeliverableActions status="approved" {...defaultProps} />);
    expect(screen.getByText('deliverable.remark')).toBeInTheDocument();
  });
});
