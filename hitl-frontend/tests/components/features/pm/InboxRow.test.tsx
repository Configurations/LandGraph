import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { InboxRow } from '../../../../src/components/features/pm/InboxRow';
import type { PMNotification } from '../../../../src/api/types';

const baseNotif: PMNotification = {
  id: '1',
  user_email: 'alice@test.com',
  type: 'assigned',
  text: 'bob assigned TEAM-001 to you',
  issue_id: 'TEAM-001',
  related_issue_id: '',
  relation_type: '',
  avatar: 'bob',
  read: false,
  created_at: new Date().toISOString(),
};

function renderRow(notification: PMNotification = baseNotif) {
  return render(
    <MemoryRouter>
      <InboxRow notification={notification} onMarkRead={vi.fn()} />
    </MemoryRouter>,
  );
}

describe('InboxRow', () => {
  it('shows unread indicator for unread notification', () => {
    const { container } = renderRow();
    const dot = container.querySelector('.bg-accent-blue');
    expect(dot).toBeTruthy();
  });

  it('hides unread indicator for read notification', () => {
    const { container } = renderRow({ ...baseNotif, read: true });
    const dots = container.querySelectorAll('.bg-accent-blue');
    expect(dots.length).toBe(0);
  });

  it('shows notification text', () => {
    renderRow();
    expect(screen.getByText('bob assigned TEAM-001 to you')).toBeInTheDocument();
  });

  it('shows issue ID as a link', () => {
    renderRow();
    const link = screen.getByText('TEAM-001');
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toBeTruthy();
  });
});
