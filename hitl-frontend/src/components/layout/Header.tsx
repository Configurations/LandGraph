import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { StatusDot } from '../ui/StatusDot';
import { useWsStore } from '../../stores/wsStore';

interface HeaderProps {
  titleKey: string;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function Header({
  titleKey,
  actions,
  children,
  className = '',
}: HeaderProps): JSX.Element {
  const { t } = useTranslation();
  const connected = useWsStore((s) => s.connected);

  return (
    <header
      className={[
        'flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface-secondary px-4 sm:px-6',
        className,
      ].join(' ')}
    >
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">{t(titleKey)}</h1>
        <StatusDot status={connected ? 'online' : 'offline'} />
      </div>
      <div className="flex items-center gap-2">
        {actions}
      </div>
      {children}
    </header>
  );
}
