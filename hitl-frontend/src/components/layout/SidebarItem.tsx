import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

interface SidebarItemProps {
  icon: ReactNode;
  labelKey: string;
  to: string;
  badge?: number;
  active?: boolean;
  onClick?: () => void;
  collapsed?: boolean;
  className?: string;
}

export function SidebarItem({
  icon,
  labelKey,
  to,
  badge,
  active = false,
  onClick,
  collapsed = false,
  className = '',
}: SidebarItemProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <Link
      to={to}
      onClick={onClick}
      title={collapsed ? t(labelKey) : undefined}
      className={[
        'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
        active
          ? 'bg-surface-active text-content-primary'
          : 'text-content-secondary hover:bg-surface-hover hover:text-content-primary',
        collapsed ? 'justify-center' : '',
        className,
      ].join(' ')}
    >
      <span className="shrink-0">{icon}</span>
      {!collapsed && <span className="flex-1 truncate">{t(labelKey)}</span>}
      {!collapsed && badge !== undefined && badge > 0 && (
        <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-accent-red px-1.5 text-[10px] font-semibold text-white">
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </Link>
  );
}
