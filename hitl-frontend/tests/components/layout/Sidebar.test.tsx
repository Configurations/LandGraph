import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Sidebar } from '../../../src/components/layout/Sidebar';
import { useAuthStore } from '../../../src/stores/authStore';
import { useTeamStore } from '../../../src/stores/teamStore';
import { useNotificationStore } from '../../../src/stores/notificationStore';

// Provide store state before each test
function setupStores(overrides: {
  user?: Record<string, unknown> | null;
  teams?: Array<{ id: string; name: string; directory: string }>;
  pendingCount?: number;
} = {}) {
  useAuthStore.setState({
    user: (overrides.user as any) ?? {
      id: '1',
      email: 'alice@test.com',
      display_name: 'Alice',
      role: 'member',
      teams: ['team1'],
    },
    isAuthenticated: true,
    token: 'fake',
    loading: false,
  });

  useTeamStore.setState({
    teams: overrides.teams ?? [
      { id: 'team1', name: 'Team Alpha', directory: 'Team1' },
    ],
    activeTeamId: 'team1',
  });

  useNotificationStore.setState({
    pendingCount: overrides.pendingCount ?? 0,
    toasts: [],
  });
}

describe('Sidebar', () => {
  it('renders inbox navigation item', () => {
    setupStores();
    render(<Sidebar />);
    expect(screen.getByText('nav.inbox')).toBeInTheDocument();
  });

  it('renders team group', () => {
    setupStores();
    render(<Sidebar />);
    expect(screen.getByText('Team Alpha')).toBeInTheDocument();
  });

  it('shows badge count when pendingCount > 0', () => {
    setupStores({ pendingCount: 5 });
    render(<Sidebar />);
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('does not show badge when pendingCount is 0', () => {
    setupStores({ pendingCount: 0 });
    render(<Sidebar />);
    expect(screen.queryByText('0')).toBeNull();
  });

  it('shows user display name', () => {
    setupStores();
    render(<Sidebar />);
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('shows user email', () => {
    setupStores();
    render(<Sidebar />);
    expect(screen.getByText('alice@test.com')).toBeInTheDocument();
  });

  it('caps badge at 99+', () => {
    setupStores({ pendingCount: 150 });
    render(<Sidebar />);
    expect(screen.getByText('99+')).toBeInTheDocument();
  });
});
