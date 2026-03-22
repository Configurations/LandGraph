import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { Input } from '../../ui/Input';
import { Select } from '../../ui/Select';
import { register } from '../../../api/auth';
import { ApiError } from '../../../api/client';

interface RegisterFormProps {
  className?: string;
}

const CULTURE_OPTIONS = [
  { value: 'fr', label: 'Francais' },
  { value: 'en', label: 'English' },
];

export function RegisterForm({ className = '' }: RegisterFormProps): JSX.Element {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [culture, setCulture] = useState('fr');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await register(email, culture);
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(t('common.error'));
      }
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className={`text-center ${className}`}>
        <div className="mb-4 text-accent-green">
          <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <p className="text-sm text-content-secondary">{t('auth.register_success')}</p>
      </div>
    );
  }

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
      <Select
        label={t('auth.culture')}
        value={culture}
        onChange={(e) => setCulture(e.target.value)}
        options={CULTURE_OPTIONS}
      />
      {error && <p className="text-sm text-accent-red">{error}</p>}
      <Button type="submit" loading={loading} className="w-full">
        {t('auth.register')}
      </Button>
    </form>
  );
}
