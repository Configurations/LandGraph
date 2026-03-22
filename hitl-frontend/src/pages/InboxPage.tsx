import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { DetailPanel } from '../components/layout/DetailPanel';
import { QuestionList } from '../components/features/hitl/QuestionList';
import { AnswerModal } from '../components/features/hitl/AnswerModal';
import { Select } from '../components/ui/Select';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { useTeamStore } from '../stores/teamStore';
import { useNotificationStore } from '../stores/notificationStore';
import { useWsStore } from '../stores/wsStore';
import * as hitlApi from '../api/hitl';
import type { QuestionResponse } from '../api/types';

export function InboxPage(): JSX.Element {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const teams = useTeamStore((s) => s.teams);
  const setPendingCount = useNotificationStore((s) => s.setPendingCount);
  const lastEvent = useWsStore((s) => s.lastEvent);

  const [questions, setQuestions] = useState<QuestionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<QuestionResponse | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const statusFilter = searchParams.get('status') ?? '';
  const teamFilter = searchParams.get('team') ?? '';

  const loadQuestions = useCallback(async () => {
    if (!activeTeamId) return;
    setLoading(true);
    try {
      const teamId = teamFilter || activeTeamId;
      const data = await hitlApi.listQuestions(teamId, {
        status: statusFilter || undefined,
      });
      setQuestions(data);
      const pending = data.filter((q) => q.status === 'pending').length;
      setPendingCount(pending);
    } catch {
      // handled by apiFetch
    } finally {
      setLoading(false);
    }
  }, [activeTeamId, statusFilter, teamFilter, setPendingCount]);

  useEffect(() => {
    void loadQuestions();
  }, [loadQuestions]);

  useEffect(() => {
    if (lastEvent?.type === 'new_question') {
      void loadQuestions();
    }
  }, [lastEvent, loadQuestions]);

  const handleAnswer = useCallback(
    async (questionId: string, response: string, action: 'approve' | 'reject' | 'answer') => {
      await hitlApi.answerQuestion(questionId, { response, action });
      setModalOpen(false);
      setSelected(null);
      void loadQuestions();
    },
    [loadQuestions],
  );

  const statusOptions = [
    { value: '', label: t('hitl.all_channels') },
    { value: 'pending', label: t('hitl.pending') },
    { value: 'answered', label: t('hitl.answered') },
    { value: 'timeout', label: t('hitl.timeout') },
  ];

  const teamOptions = [
    { value: '', label: t('hitl.filter_team') },
    ...teams.map((team) => ({ value: team.id, label: team.name })),
  ];

  const updateFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams);
    if (value) params.set(key, value);
    else params.delete(key);
    setSearchParams(params);
  };

  const pendingCount = questions.filter((q) => q.status === 'pending').length;

  return (
    <PageContainer>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold">{t('hitl.questions')}</h2>
          {pendingCount > 0 && (
            <Badge color="red" variant="count">{pendingCount}</Badge>
          )}
        </div>
        <div className="flex gap-2">
          <Select
            options={statusOptions}
            value={statusFilter}
            onChange={(e) => updateFilter('status', e.target.value)}
            className="w-36"
          />
          <Select
            options={teamOptions}
            value={teamFilter}
            onChange={(e) => updateFilter('team', e.target.value)}
            className="w-36"
          />
        </div>
      </div>

      <QuestionList
        questions={questions}
        loading={loading}
        onQuestionClick={(q) => {
          setSelected(q);
          setModalOpen(true);
        }}
        onApprove={(q) => handleAnswer(q.id, '', 'approve')}
        onReject={(q) => handleAnswer(q.id, '', 'reject')}
      />

      <AnswerModal
        question={selected}
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setSelected(null);
        }}
        onSubmit={handleAnswer}
      />
    </PageContainer>
  );
}
