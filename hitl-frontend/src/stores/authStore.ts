import { create } from 'zustand';
import * as authApi from '../api/auth';
import { clearToken, getToken, setToken } from '../api/client';
import type { UserResponse } from '../api/types';

interface AuthState {
  token: string | null;
  user: UserResponse | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (credential: string) => Promise<void>;
  logout: () => void;
  setUser: (user: UserResponse) => void;
  loadUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: getToken(),
  user: null,
  isAuthenticated: !!getToken(),
  loading: false,

  login: async (email, password) => {
    set({ loading: true });
    try {
      const response = await authApi.login(email, password);
      setToken(response.token);
      set({
        token: response.token,
        user: response.user,
        isAuthenticated: true,
        loading: false,
      });
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  loginWithGoogle: async (credential) => {
    set({ loading: true });
    try {
      const response = await authApi.googleAuth(credential);
      setToken(response.token);
      set({
        token: response.token,
        user: response.user,
        isAuthenticated: true,
        loading: false,
      });
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  logout: () => {
    clearToken();
    set({ token: null, user: null, isAuthenticated: false });
  },

  setUser: (user) => set({ user }),

  loadUser: async () => {
    if (!get().token) return;
    set({ loading: true });
    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, loading: false });
    } catch {
      get().logout();
      set({ loading: false });
    }
  },
}));
