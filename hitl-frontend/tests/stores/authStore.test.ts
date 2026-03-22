import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useAuthStore } from '../../src/stores/authStore';

// Mock api modules
vi.mock('../../src/api/auth', () => ({
  login: vi.fn(),
  googleAuth: vi.fn(),
  getMe: vi.fn(),
}));

vi.mock('../../src/api/client', () => ({
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  clearToken: vi.fn(),
}));

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: null,
      user: null,
      isAuthenticated: false,
      loading: false,
    });
  });

  it('initial state is unauthenticated', () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });

  it('login sets token and user', async () => {
    const mockUser = {
      id: '1',
      email: 'a@b.com',
      display_name: 'Alice',
      role: 'member' as const,
      teams: ['team1'],
    };
    const authApi = await import('../../src/api/auth');
    (authApi.login as ReturnType<typeof vi.fn>).mockResolvedValue({
      token: 'jwt-123',
      user: mockUser,
    });

    await useAuthStore.getState().login('a@b.com', 'pass');

    const state = useAuthStore.getState();
    expect(state.token).toBe('jwt-123');
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
    expect(state.loading).toBe(false);
  });

  it('login sets loading false on error', async () => {
    const authApi = await import('../../src/api/auth');
    (authApi.login as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('fail'));

    await expect(useAuthStore.getState().login('x', 'y')).rejects.toThrow('fail');

    expect(useAuthStore.getState().loading).toBe(false);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('logout clears state', () => {
    useAuthStore.setState({
      token: 'jwt',
      user: { id: '1', email: 'a@b.com', display_name: 'A', role: 'member', teams: [] },
      isAuthenticated: true,
    });

    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it('setUser updates user', () => {
    const user = {
      id: '2',
      email: 'b@c.com',
      display_name: 'Bob',
      role: 'admin' as const,
      teams: ['t1'],
    };
    useAuthStore.getState().setUser(user);
    expect(useAuthStore.getState().user).toEqual(user);
  });

  it('token is persisted via setToken', async () => {
    const clientModule = await import('../../src/api/client');
    const authApi = await import('../../src/api/auth');

    (authApi.login as ReturnType<typeof vi.fn>).mockResolvedValue({
      token: 'persisted-jwt',
      user: { id: '1', email: 'a@b.com', display_name: 'A', role: 'member', teams: [] },
    });

    await useAuthStore.getState().login('a@b.com', 'pass');

    expect(clientModule.setToken).toHaveBeenCalledWith('persisted-jwt');
  });
});
