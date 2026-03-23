import { useTranslation } from 'react-i18next';

interface GitStatusBadgeProps {
  connected: boolean;
  repoExists: boolean;
  className?: string;
}

export function GitStatusBadge({ connected, repoExists, className = '' }: GitStatusBadgeProps): JSX.Element {
  const { t } = useTranslation();

  if (!connected) {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold bg-accent-red/20 text-accent-red ${className}`}>
        {t('git.connection_error')}
      </span>
    );
  }

  if (repoExists) {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold bg-accent-yellow/20 text-accent-yellow ${className}`}>
        {t('git.repo_exists_warning')}
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold bg-accent-green/20 text-accent-green ${className}`}>
      {t('git.repo_not_found')}
    </span>
  );
}
