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
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          }
          labelKey="nav.dashboard"
          to="/dashboard"
          active={location.pathname === '/dashboard'}
        />

        <SidebarItem
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          }
          labelKey="nav.issues"
          to="/issues"
          active={location.pathname === '/issues'}
        />

        <SidebarItem
          icon={inboxIcon}
          labelKey="nav.inbox"
          to="/inbox"
          badge={pendingCount}
          active={location.pathname === '/inbox'}
        />

        <SidebarItem
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          }
          labelKey="project.projects"
          to="/projects"
          active={location.pathname.startsWith('/projects')}
        />

        <SidebarItem
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
            </svg>
          }
          labelKey="nav.reviews"
          to="/reviews"
          active={location.pathname === '/reviews'}
        />

        <SidebarItem
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          }
          labelKey="nav.pulse"
          to="/pulse"
          active={location.pathname === '/pulse'}
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
                <SidebarItem
                  icon={
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                  }
                  labelKey="nav.agents"
                  to={`/teams/${team.id}/agents`}
                  active={location.pathname.startsWith(`/teams/${team.id}/agents`)}
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
