import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useNotificationStore } from '../../stores/notificationStore';
import { useTeamStore } from '../../stores/teamStore';

interface MobileNavProps {
  className?: string;
}

interface NavItem {
  labelKey: string;
  to: string;
  icon: string;
  badge?: number;
}

const iconPaths: Record<string, string> = {
  inbox: 'M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4',
  teams: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z',
  settings: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z',
  profile: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z',
};

export function MobileNav({ className = '' }: MobileNavProps): JSX.Element {
  const { t } = useTranslation();
  const location = useLocation();
  const pendingCount = useNotificationStore((s) => s.pendingCount);
  const activeTeamId = useTeamStore((s) => s.activeTeamId);

  const items: NavItem[] = [
    { labelKey: 'nav.inbox', to: '/inbox', icon: 'inbox', badge: pendingCount },
    { labelKey: 'nav.teams', to: activeTeamId ? `/teams/${activeTeamId}/members` : '/inbox', icon: 'teams' },
    { labelKey: 'nav.settings', to: '/inbox', icon: 'settings' },
    { labelKey: 'nav.profile', to: '/inbox', icon: 'profile' },
  ];

  return (
    <nav
      className={[
        'fixed bottom-0 left-0 right-0 z-40 flex items-center justify-around',
        'border-t border-border bg-surface-secondary py-2',
        className,
      ].join(' ')}
    >
      {items.map((item) => {
        const isActive = location.pathname === item.to;
        return (
          <Link
            key={item.labelKey}
            to={item.to}
            className={[
              'relative flex flex-col items-center gap-0.5 px-3 py-1 text-[10px]',
              isActive ? 'text-accent-blue' : 'text-content-tertiary',
            ].join(' ')}
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={iconPaths[item.icon]} />
            </svg>
            <span>{t(item.labelKey)}</span>
            {item.badge !== undefined && item.badge > 0 && (
              <span className="absolute -top-0.5 right-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-accent-red px-1 text-[9px] font-bold text-white">
                {item.badge > 99 ? '99+' : item.badge}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
