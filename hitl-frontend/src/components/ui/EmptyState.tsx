import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface EmptyStateProps {
  icon?: ReactNode;
  titleKey: string;
  descriptionKey?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  titleKey,
  descriptionKey,
  action,
  className = '',
}: EmptyStateProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={`flex flex-col items-center justify-center py-16 px-4 text-center ${className}`}>
      {icon && (
        <div className="mb-4 text-content-quaternary">{icon}</div>
      )}
      <h3 className="text-lg font-semibold text-content-secondary">{t(titleKey)}</h3>
      {descriptionKey && (
        <p className="mt-2 max-w-sm text-sm text-content-tertiary">{t(descriptionKey)}</p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
