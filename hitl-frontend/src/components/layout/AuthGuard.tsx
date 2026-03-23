import { type ReactNode, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { Spinner } from '../ui/Spinner';

interface AuthGuardProps {
  children: ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps): JSX.Element {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);
  const loading = useAuthStore((s) => s.loading);
  const navigate = useNavigate();
  const didInit = useRef(false);

  useEffect(() => {
    if (!didInit.current && isAuthenticated && !user && !loading) {
      didInit.current = true;
      useAuthStore.getState().loadUser();
    }
  }, [isAuthenticated, user, loading]);

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/login', { replace: true });
    }
  }, [isAuthenticated, loading, navigate]);

  if (loading || (isAuthenticated && !user)) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-primary">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <div />;
  }

  return <>{children}</>;
}
