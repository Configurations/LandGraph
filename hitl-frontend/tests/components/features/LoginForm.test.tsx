import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LoginForm } from '../../../src/components/features/auth/LoginForm';
import { useAuthStore } from '../../../src/stores/authStore';
import { ApiError } from '../../../src/api/client';

// Mock GoogleSignIn to avoid external dependencies
vi.mock('../../../src/components/features/auth/GoogleSignIn', () => ({
  GoogleSignIn: () => <div data-testid="google-signin" />,
}));

describe('LoginForm', () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: null,
      user: null,
      isAuthenticated: false,
      loading: false,
    });
  });

  it('renders email and password inputs', () => {
    render(<LoginForm />);
    expect(screen.getByLabelText('auth.email')).toBeInTheDocument();
    expect(screen.getByLabelText('auth.password')).toBeInTheDocument();
  });

  it('renders submit button', () => {
    render(<LoginForm />);
    expect(screen.getByRole('button', { name: 'auth.login' })).toBeInTheDocument();
  });

  it('calls login on submit', async () => {
    const loginMock = vi.fn().mockResolvedValue(undefined);
    useAuthStore.setState({ login: loginMock });

    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText('auth.email'), {
      target: { value: 'alice@test.com' },
    });
    fireEvent.change(screen.getByLabelText('auth.password'), {
      target: { value: 'secret' },
    });
    fireEvent.submit(screen.getByRole('button', { name: 'auth.login' }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith('alice@test.com', 'secret');
    });
  });

  it('shows error on failed login (401)', async () => {
    const loginMock = vi.fn().mockRejectedValue(new ApiError(401, 'bad'));
    useAuthStore.setState({ login: loginMock });

    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText('auth.email'), {
      target: { value: 'x@y.com' },
    });
    fireEvent.change(screen.getByLabelText('auth.password'), {
      target: { value: 'wrong' },
    });
    fireEvent.submit(screen.getByRole('button', { name: 'auth.login' }));

    await waitFor(() => {
      expect(screen.getByText('auth.invalid_credentials')).toBeInTheDocument();
    });
  });

  it('shows pending error on 403', async () => {
    const loginMock = vi.fn().mockRejectedValue(new ApiError(403, 'pending'));
    useAuthStore.setState({ login: loginMock });

    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText('auth.email'), {
      target: { value: 'x@y.com' },
    });
    fireEvent.change(screen.getByLabelText('auth.password'), {
      target: { value: 'pass' },
    });
    fireEvent.submit(screen.getByRole('button', { name: 'auth.login' }));

    await waitFor(() => {
      expect(screen.getByText('auth.account_pending')).toBeInTheDocument();
    });
  });

  it('disables button while loading', () => {
    useAuthStore.setState({ loading: true });
    render(<LoginForm />);
    const btn = screen.getByRole('button', { name: 'auth.login' });
    expect(btn).toBeDisabled();
  });
});
