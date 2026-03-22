import { useCallback, useEffect, useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import type { UserResponse } from '../api/types';

interface UseAuthReturn {
  user: UserResponse | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export function useAuth(): UseAuthReturn {
  const store = useAuthStore();
  const [initialLoad, setInitialLoad] = useState(!store.user && store.isAuthenticated);

  useEffect(() => {
    if (initialLoad) {
      store.loadUser().finally(() => setInitialLoad(false));
    }
  }, [initialLoad, store]);

  const login = useCallback(
    async (email: string, password: string) => {
      await store.login(email, password);
    },
    [store],
  );

  return {
    user: store.user,
    isAuthenticated: store.isAuthenticated,
    loading: store.loading || initialLoad,
    login,
    logout: store.logout,
  };
}
