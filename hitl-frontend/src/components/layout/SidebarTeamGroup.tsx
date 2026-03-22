import type { ReactNode } from 'react';

interface TeamInfo {
  id: string;
  name: string;
}

interface SidebarTeamGroupProps {
  team: TeamInfo;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
  className?: string;
}

export function SidebarTeamGroup({
  team,
  expanded,
  onToggle,
  children,
  className = '',
}: SidebarTeamGroupProps): JSX.Element {
  return (
    <div className={className}>
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-content-tertiary hover:text-content-secondary transition-colors"
      >
        <svg
          className={`h-3 w-3 transition-transform ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span className="truncate">{team.name}</span>
      </button>
      {expanded && <div className="ml-2 mt-1 flex flex-col gap-0.5">{children}</div>}
    </div>
  );
}
