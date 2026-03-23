import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { QuestionList } from '../components/features/hitl/QuestionList';
import { AnswerModal } from '../components/features/hitl/AnswerModal';
import { InboxList } from '../components/features/pm/InboxList';
import { InboxBadge } from '../components/features/pm/InboxBadge';
import { Select } from '../components/ui/Select';
import { Badge } from '../components/ui/Badge';
import { useTeamStore } from '../stores/teamStore';
import { useProjectStore } from '../stores/projectStore';
import { useNotificationStore } from '../stores/notificationStore';
import { useInboxStore } from '../stores/inboxStore';
import { useWsStore } from '../stores/wsStore';
import * as hitlApi from '../api/hitl';
import * as workflowApi from '../api/workflow';
import type { ProjectWorkflowResponse, QuestionResponse } from '../api/types';

type InboxTab = 'questions' | 'notifications';

export function InboxPage(): JSX.Element {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const teams = useTeamStore((s) => s.teams);
  const activeSlug = useProjectStore((s) => s.activeSlug);
  // setPendingCount called via getState() to avoid re-render loops
  const lastEvent = useWsStore((s) => s.lastEvent);

  const notifications = useInboxStore((s) => s.notifications);
  const unreadCount = useInboxStore((s) => s.unreadCount);

  const [questions, setQuestions] = useState<QuestionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<QuestionResponse | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<InboxTab>('questions');
  const [projectWorkflows, setProjectWorkflows] = useState<ProjectWorkflowResponse[]>([]);

  const statusFilter = searchParams.get('status') ?? '';
  const teamFilter = searchParams.get('team') ?? '';
  const workflowFilter = searchParams.get('workflow') ?? '';

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
      useNotificationStore.getState().setPendingCount(pending);
    } catch {
      // handled by apiFetch
    } finally {
      setLoading(false);
    }
  }, [activeTeamId, statusFilter, teamFilter]);

  useEffect(() => {
    void loadQuestions();
    useInboxStore.getState().loadNotifications();
  }, [loadQuestions]);

  useEffect(() => {
    if (!activeSlug) { setProjectWorkflows([]); return; }
    workflowApi.listProjectWorkflows(activeSlug)
      .then(setProjectWorkflows)
      .catch(() => setProjectWorkflows([]));
  }, [activeSlug]);

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
  const combinedBadge = pendingCount + unreadCount;

  return (
    <PageContainer>
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-xl font-semibold">{t('nav.inbox')}</h2>
        {combinedBadge > 0 && <Badge color="red" variant="count">{combinedBadge}</Badge>}
      </div>

      <div className="flex items-center gap-1 border-b border-border mb-4">
        <button
          onClick={() => setActiveTab('questions')}
          className={[
            'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
            activeTab === 'questions'
              ? 'border-accent-blue text-accent-blue'
              : 'border-transparent text-content-tertiary hover:text-content-primary',
          ].join(' ')}
        >
          {t('hitl.questions')}
          {pendingCount > 0 && <Badge color="red" variant="count" size="sm" className="ml-2">{pendingCount}</Badge>}
        </button>
        <button
          onClick={() => setActiveTab('notifications')}
          className={[
            'flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors',
            activeTab === 'notifications'
              ? 'border-accent-blue text-accent-blue'
              : 'border-transparent text-content-tertiary hover:text-content-primary',
          ].join(' ')}
        >
          {t('inbox.notifications')}
          <InboxBadge count={unreadCount} />
        </button>
      </div>

      {activeTab === 'questions' && (
        <>
          <div className="flex gap-2 mb-4">
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
            {projectWorkflows.length > 0 && (
              <Select
                options={[
                  { value: '', label: t('multi_workflow.all_workflows') },
                  ...projectWorkflows.map((w) => ({ value: w.id, label: w.name })),
                ]}
                value={workflowFilter}
                onChange={(e) => updateFilter('workflow', e.target.value)}
                className="w-44"
              />
            )}
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
        </>
      )}

      {activeTab === 'notifications' && (
        <InboxList
          notifications={notifications}
          onMarkRead={(id) => useInboxStore.getState().markAsRead(id)}
          onMarkAllRead={() => useInboxStore.getState().markAllAsRead()}
        />
      )}
    </PageContainer>
  );
}
