import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SidebarItem } from './SidebarItem';
import { SidebarTeamGroup } from './SidebarTeamGroup';
import { Avatar } from '../ui/Avatar';
import { useAuthStore } from '../../stores/authStore';
import { useTeamStore } from '../../stores/teamStore';
import { useNotificationStore } from '../../stores/notificationStore';

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className = '' }: SidebarProps): JSX.Element {
  const { t } = useTranslation();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const teams = useTeamStore((s) => s.teams);
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const setActiveTeam = useTeamStore((s) => s.setActiveTeam);
  const pendingCount = useNotificationStore((s) => s.pendingCount);
  const [expandedTeams, setExpandedTeams] = useState<Set<string>>(
    new Set(activeTeamId ? [activeTeamId] : []),
  );

  const toggleTeam = (id: string) => {
    setExpandedTeams((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setActiveTeam(id);
  };

  const inboxIcon = (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
    </svg>
  );

  const membersIcon = (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197m13.5-9a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
    </svg>
  );

  return (
    <div className={`flex w-[220px] flex-col bg-surface-secondary border-r border-border ${className}`}>
      <div className="flex h-14 items-center gap-2 px-4 border-b border-border">
        <span className="text-lg font-bold text-accent-blue">ag.flow</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <SidebarItem
          icon={inboxIcon}
          labelKey="nav.inbox"
          to="/inbox"
          badge={pendingCount}
          active={location.pathname === '/inbox'}
        />

        {teams.length > 0 && (
          <div className="mt-6">
            <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest text-content-quaternary">
              {t('nav.teams')}
            </p>
            {teams.map((team) => (
              <SidebarTeamGroup
                key={team.id}
                team={team}
                expanded={expandedTeams.has(team.id)}
                onToggle={() => toggleTeam(team.id)}
              >
                <SidebarItem
                  icon={membersIcon}
                  labelKey="nav.members"
                  to={`/teams/${team.id}/members`}
                  active={location.pathname === `/teams/${team.id}/members`}
                />
              </SidebarTeamGroup>
            ))}
          </div>
        )}
      </nav>

      {user && (
        <div className="border-t border-border px-3 py-3">
          <div className="flex items-center gap-3">
            <Avatar name={user.display_name} size="sm" />
            <div className="flex-1 min-w-0">
              <p className="truncate text-sm font-medium">{user.display_name}</p>
              <p className="truncate text-xs text-content-tertiary">{user.email}</p>
            </div>
            <button
              onClick={logout}
              title={t('common.logout')}
              className="text-content-tertiary hover:text-content-primary transition-colors"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
