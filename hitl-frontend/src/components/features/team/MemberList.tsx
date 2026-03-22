import { useTranslation } from 'react-i18next';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import { Button } from '../../ui/Button';
import { StatusDot } from '../../ui/StatusDot';
import { EmptyState } from '../../ui/EmptyState';
import type { MemberResponse } from '../../../api/types';

interface MemberListProps {
  members: MemberResponse[];
  onInvite?: () => void;
  onRemove?: (userId: string) => void;
  isAdmin: boolean;
  className?: string;
}

function MemberRow({
  member,
  onRemove,
  isAdmin,
}: {
  member: MemberResponse;
  onRemove?: (userId: string) => void;
  isAdmin: boolean;
}): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-3 rounded-lg px-3 py-3 hover:bg-surface-hover transition-colors">
      <Avatar name={member.display_name} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">{member.display_name}</span>
          <StatusDot status={member.is_active ? 'online' : 'offline'} />
        </div>
        <p className="text-xs text-content-tertiary truncate">{member.email}</p>
      </div>
      <Badge
        color={member.team_role === 'admin' ? 'purple' : 'blue'}
        size="sm"
      >
        {t(`team.role_${member.team_role}`)}
      </Badge>
      <Badge color="green" size="sm" variant="tag">
        {member.auth_type}
      </Badge>
      {isAdmin && onRemove && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onRemove(member.id)}
          className="text-accent-red hover:text-accent-red"
        >
          {t('team.remove')}
        </Button>
      )}
    </div>
  );
}

export function MemberList({
  members,
  onInvite,
  onRemove,
  isAdmin,
  className = '',
}: MemberListProps): JSX.Element {
  const { t } = useTranslation();

  if (members.length === 0) {
    return (
      <EmptyState
        titleKey="common.no_results"
        action={
          isAdmin && onInvite ? (
            <Button onClick={onInvite}>{t('team.invite')}</Button>
          ) : undefined
        }
        className={className}
      />
    );
  }

  return (
    <div className={`flex flex-col divide-y divide-border ${className}`}>
      {members.map((member) => (
        <MemberRow
          key={member.id}
          member={member}
          onRemove={onRemove}
          isAdmin={isAdmin}
        />
      ))}
    </div>
  );
}
