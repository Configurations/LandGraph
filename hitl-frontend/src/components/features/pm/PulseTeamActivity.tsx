import { useTranslation } from 'react-i18next';
import { Card } from '../../ui/Card';
import type { TeamMemberActivity } from '../../../api/types';

interface PulseTeamActivityProps {
  members: TeamMemberActivity[];
  className?: string;
}

export function PulseTeamActivity({ members, className = '' }: PulseTeamActivityProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <Card className={className}>
      <h3 className="text-sm font-semibold mb-3">{t('pulse.team_activity')}</h3>
      {members.length === 0 ? (
        <p className="text-xs text-content-tertiary">{t('pulse.no_activity')}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {members.map((member) => {
            const pct = member.total > 0 ? (member.completed / member.total) * 100 : 0;
            return (
              <div key={member.name} className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-content-primary">{member.name}</span>
                  <span className="text-xs text-content-tertiary">
                    {member.completed}/{member.total}
                  </span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-surface-tertiary overflow-hidden">
                  <div
                    className="h-full rounded-full bg-accent-green transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
