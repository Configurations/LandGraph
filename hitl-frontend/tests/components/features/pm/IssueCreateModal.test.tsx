import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IssueCreateModal } from '../../../../src/components/features/pm/IssueCreateModal';

describe('IssueCreateModal', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onCreated: vi.fn(),
    teamId: 'team1',
  };

  it('renders all form fields when open', () => {
    render(<IssueCreateModal {...defaultProps} />);
    expect(screen.getByText('issue.title')).toBeInTheDocument();
    expect(screen.getByText('issue.description')).toBeInTheDocument();
    expect(screen.getByText('issue.priority')).toBeInTheDocument();
    expect(screen.getByText('issue.status')).toBeInTheDocument();
    expect(screen.getByText('issue.assignee')).toBeInTheDocument();
    expect(screen.getByText('issue.tags')).toBeInTheDocument();
  });

  it('save button is disabled when title is empty', () => {
    render(<IssueCreateModal {...defaultProps} />);
    const saveBtn = screen.getByText('common.save');
    expect(saveBtn).toBeDisabled();
  });

  it('submit calls onCreated with payload', () => {
    const onCreated = vi.fn();
    render(<IssueCreateModal {...defaultProps} onCreated={onCreated} />);

    // Find the title input and type
    const inputs = screen.getAllByRole('textbox');
    const titleInput = inputs[0];
    fireEvent.change(titleInput, { target: { value: 'New Issue' } });

    // Click save
    const saveBtn = screen.getByText('common.save');
    fireEvent.click(saveBtn);

    expect(onCreated).toHaveBeenCalledOnce();
    expect(onCreated.mock.calls[0][0].title).toBe('New Issue');
  });

  it('returns null when not open', () => {
    const { container } = render(
      <IssueCreateModal {...defaultProps} open={false} />,
    );
    // Modal should not render content when closed
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });
});
