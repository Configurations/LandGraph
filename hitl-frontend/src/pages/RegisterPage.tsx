import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RegisterForm } from '../components/features/auth/RegisterForm';

export function RegisterPage(): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-primary px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-accent-blue">ag.flow</h1>
          <p className="mt-2 text-sm text-content-tertiary">Manager</p>
        </div>
        <div className="rounded-xl border border-border bg-surface-secondary p-6">
          <h2 className="mb-6 text-lg font-semibold text-center">{t('auth.register')}</h2>
          <RegisterForm />
          <div className="mt-4 text-center">
            <Link to="/login" className="text-sm text-accent-blue hover:underline">
              {t('common.back')} {t('auth.login')}
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
