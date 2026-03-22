import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { GitStatusBadge } from './GitStatusBadge';
import { useProjectStore } from '../../../stores/projectStore';
import * as projectsApi from '../../../api/projects';
import type { GitTestPayload } from '../../../api/types';

interface WizardStepGitProps {
  className?: string;
}

type ServiceType = 'other' | 'github' | 'gitlab' | 'gitea' | 'forgejo' | 'bitbucket';

const SERVICE_URLS: Record<ServiceType, string> = {
  other: '',
  github: 'https://github.com',
  gitlab: 'https://gitlab.com',
  gitea: '',
  forgejo: '',
  bitbucket: 'https://bitbucket.org',
};

const SERVICE_OPTIONS: ServiceType[] = ['other', 'github', 'gitlab', 'gitea', 'forgejo', 'bitbucket'];

export function WizardStepGit({ className = '' }: WizardStepGitProps): JSX.Element {
  const { t } = useTranslation();
  const wizardData = useProjectStore((s) => s.wizardData);
  const updateWizardData = useProjectStore((s) => s.updateWizardData);

  const [service, setService] = useState<ServiceType>('other');
  const [url, setUrl] = useState('');
  const [login, setLogin] = useState('');
  const [token, setToken] = useState('');
  const [repoName, setRepoName] = useState(wizardData.slug || '');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ connected: boolean; repoExists: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleServiceChange = useCallback((value: ServiceType) => {
    setService(value);
    const defaultUrl = SERVICE_URLS[value];
    if (defaultUrl) setUrl(defaultUrl);
    setTestResult(null);
    setError(null);
  }, []);

  const buildConfig = useCallback((): GitTestPayload => ({
    service,
    url,
    login,
    token,
    repo_name: repoName,
  }), [service, url, login, token, repoName]);

  const handleTest = useCallback(async () => {
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const slug = wizardData.slug || 'temp';
      const result = await projectsApi.testGitConnection(slug, buildConfig());
      setTestResult({ connected: result.connected, repoExists: result.repo_exists });
      if (result.connected) {
        updateWizardData({ gitConfig: buildConfig() });
      }
      if (result.error) setError(result.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  }, [wizardData.slug, buildConfig, updateWizardData]);

  const serviceLabel = (s: ServiceType): string =>
    s === 'other' ? t('git.other') : s.charAt(0).toUpperCase() + s.slice(1);

  return (
    <div className={`flex flex-col gap-4 max-w-md ${className}`}>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-secondary">{t('git.service')}</span>
        <select
          value={service}
          onChange={(e) => handleServiceChange(e.target.value as ServiceType)}
          className="rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:border-accent-blue focus:outline-none"
        >
          {SERVICE_OPTIONS.map((s) => (
            <option key={s} value={s}>{serviceLabel(s)}</option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-secondary">{t('git.url')}</span>
        <input type="text" value={url} onChange={(e) => setUrl(e.target.value)}
          className="rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:border-accent-blue focus:outline-none" />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-secondary">{t('git.login')}</span>
        <input type="text" value={login} onChange={(e) => setLogin(e.target.value)}
          className="rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:border-accent-blue focus:outline-none" />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-secondary">{t('git.token')}</span>
        <input type="password" value={token} onChange={(e) => setToken(e.target.value)}
          className="rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:border-accent-blue focus:outline-none" />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-secondary">{t('git.repo_name')}</span>
        <input type="text" value={repoName} onChange={(e) => setRepoName(e.target.value)}
          className="rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:border-accent-blue focus:outline-none" />
      </label>

      <div className="flex items-center gap-3">
        <Button onClick={() => void handleTest()} loading={testing} size="sm">
          {t('git.test_connection')}
        </Button>
        {testResult && <GitStatusBadge connected={testResult.connected} repoExists={testResult.repoExists} />}
      </div>

      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
