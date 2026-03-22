import { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LoginForm } from '../components/features/auth/LoginForm';
import { useAuthStore } from '../stores/authStore';

export function LoginPage(): JSX.Element {
  const { t } = useTranslation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/inbox', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-primary px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-accent-blue">ag.flow</h1>
          <p className="mt-2 text-sm text-content-tertiary">Manager</p>
        </div>
        <div className="rounded-xl border border-border bg-surface-secondary p-6">
          <h2 className="mb-6 text-lg font-semibold text-center">{t('auth.login')}</h2>
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
