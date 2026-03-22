import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { MemberList } from '../components/features/team/MemberList';
import { InviteMemberModal } from '../components/features/team/InviteMemberModal';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { useAuthStore } from '../stores/authStore';
import { useTeamStore } from '../stores/teamStore';
import * as teamsApi from '../api/teams';
import type { MemberResponse } from '../api/types';

export function TeamMembersPage(): JSX.Element {
  const { t } = useTranslation();
  const { teamId } = useParams<{ teamId: string }>();
  const user = useAuthStore((s) => s.user);
  const teams = useTeamStore((s) => s.teams);

  const [members, setMembers] = useState<MemberResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);

  const isAdmin = user?.role === 'admin';
  const team = teams.find((tm) => tm.id === teamId);

  const loadMembers = useCallback(async () => {
    if (!teamId) return;
    setLoading(true);
    try {
      const data = await teamsApi.listMembers(teamId);
      setMembers(data);
    } catch {
      // handled by apiFetch
    } finally {
      setLoading(false);
    }
  }, [teamId]);

  useEffect(() => {
    void loadMembers();
  }, [loadMembers]);

  const handleInvite = async (email: string, displayName: string, role: string) => {
    if (!teamId) return;
    await teamsApi.inviteMember(teamId, { email, display_name: displayName, role });
    void loadMembers();
  };

  const handleRemove = async (userId: string) => {
    if (!teamId) return;
    await teamsApi.removeMember(teamId, userId);
    void loadMembers();
  };

  if (loading) {
    return (
      <PageContainer className="flex justify-center py-12">
        <Spinner size="lg" />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold">
            {team?.name ?? teamId} - {t('nav.members')}
          </h2>
          <p className="text-sm text-content-tertiary mt-1">
            {members.length} {t('team.members')}
          </p>
        </div>
        {isAdmin && (
          <Button onClick={() => setInviteOpen(true)}>
            {t('team.invite')}
          </Button>
        )}
      </div>

      <MemberList
        members={members}
        isAdmin={isAdmin}
        onInvite={() => setInviteOpen(true)}
        onRemove={handleRemove}
      />

      {teamId && (
        <InviteMemberModal
          open={inviteOpen}
          onClose={() => setInviteOpen(false)}
          onInvite={handleInvite}
          teamId={teamId}
        />
      )}
    </PageContainer>
  );
}
