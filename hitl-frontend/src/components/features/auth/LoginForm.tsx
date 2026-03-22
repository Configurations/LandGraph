import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Button } from '../../ui/Button';
import { Input } from '../../ui/Input';
import { GoogleSignIn } from './GoogleSignIn';
import { useAuthStore } from '../../../stores/authStore';
import { ApiError } from '../../../api/client';

interface LoginFormProps {
  className?: string;
}

export function LoginForm({ className = '' }: LoginFormProps): JSX.Element {
  const { t } = useTranslation();
  const login = useAuthStore((s) => s.login);
  const loading = useAuthStore((s) => s.loading);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setError(t('auth.account_pending'));
        } else {
          setError(t('auth.invalid_credentials'));
        }
      } else {
        setError(t('common.error'));
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} className={`flex flex-col gap-4 ${className}`}>
      <Input
        label={t('auth.email')}
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        autoComplete="email"
      />
      <Input
        label={t('auth.password')}
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        autoComplete="current-password"
      />
      {error && <p className="text-sm text-accent-red">{error}</p>}
      <Button type="submit" loading={loading} className="w-full">
        {t('auth.login')}
      </Button>
      <GoogleSignIn />
      <div className="flex justify-between text-sm">
        <Link to="/register" className="text-accent-blue hover:underline">
          {t('auth.register')}
        </Link>
        <Link to="/reset-password" className="text-content-tertiary hover:text-content-secondary">
          {t('auth.forgot_password')}
        </Link>
      </div>
    </form>
  );
}
