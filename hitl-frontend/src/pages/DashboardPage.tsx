import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { OverviewCards } from '../components/features/dashboard/OverviewCards';
import { ActiveTasksList } from '../components/features/dashboard/ActiveTasksList';
import { CostSummaryCard } from '../components/features/dashboard/CostSummaryCard';
import { CostByAgentChart } from '../components/features/dashboard/CostByAgentChart';
import { IssueRow } from '../components/features/pm/IssueRow';
import { ActivityTimeline } from '../components/features/pm/ActivityTimeline';
import { WorkflowCard } from '../components/features/project/WorkflowCard';
import { Spinner } from '../components/ui/Spinner';
import { useTeamStore } from '../stores/teamStore';
import { useProjectStore } from '../stores/projectStore';
import { useWsStore } from '../stores/wsStore';
import * as dashboardApi from '../api/dashboard';
import * as issuesApi from '../api/issues';
import * as activityApi from '../api/activity';
import * as workflowApi from '../api/workflow';
import type { ActiveTask, ActivityEntry, CostSummary, IssueResponse, OverviewData, ProjectWorkflowResponse } from '../api/types';

const RECENT_ISSUES_LIMIT = 5;
const RECENT_ACTIVITY_LIMIT = 10;

export function DashboardPage(): JSX.Element {
  const { t } = useTranslation();
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const activeSlug = useProjectStore((s) => s.activeSlug);
  const lastEvent = useWsStore((s) => s.lastEvent);

  const [overview, setOverview] = useState<OverviewData>({ pending_questions: 0, active_tasks: 0, total_cost: 0 });
  const [tasks, setTasks] = useState<ActiveTask[]>([]);
  const [costs, setCosts] = useState<CostSummary[]>([]);
  const [recentIssues, setRecentIssues] = useState<IssueResponse[]>([]);
  const [activityEntries, setActivityEntries] = useState<ActivityEntry[]>([]);
  const [activeWorkflows, setActiveWorkflows] = useState<ProjectWorkflowResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [ov, tk] = await Promise.all([
          dashboardApi.getOverview(activeTeamId ?? undefined),
          dashboardApi.getActiveTasks(activeTeamId ?? undefined),
        ]);
        setOverview(ov);
        setTasks(tk);

        if (activeSlug) {
          const c = await dashboardApi.getProjectCosts(activeSlug);
          setCosts(c);
        }

        try {
          const issues = await issuesApi.listIssues(
            activeTeamId ? { team_id: activeTeamId } : undefined,
          );
          setRecentIssues(issues.slice(0, RECENT_ISSUES_LIMIT));
        } catch {
          // issues endpoint may not be available yet
        }

        if (activeSlug) {
          try {
            const activity = await activityApi.getProjectActivity(activeSlug, RECENT_ACTIVITY_LIMIT);
            setActivityEntries(activity);
          } catch {
            // activity endpoint may not be available yet
          }
          try {
            const wfs = await workflowApi.listProjectWorkflows(activeSlug);
            setActiveWorkflows(wfs.filter((w) => w.status === 'active'));
          } catch {
            // workflows endpoint may not be available yet
          }
        }
      } catch {
        // handled by apiFetch
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [activeTeamId, activeSlug, lastEvent]);

  const handleWorkflowAction = useCallback(
    async (action: 'activate' | 'pause' | 'complete' | 'relaunch', id: string) => {
      if (!activeSlug) return;
      const fn = { activate: workflowApi.activateWorkflow, pause: workflowApi.pauseWorkflow, complete: workflowApi.completeWorkflow, relaunch: workflowApi.relaunchWorkflow }[action];
      await fn(activeSlug, id);
      const wfs = await workflowApi.listProjectWorkflows(activeSlug);
      setActiveWorkflows(wfs.filter((w) => w.status === 'active'));
    },
    [activeSlug],
  );

  if (loading) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center py-12">
          <Spinner />
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <h2 className="text-xl font-semibold mb-6">{t('dashboard.title')}</h2>
      <div className="flex flex-col gap-6">
        <OverviewCards data={overview} />
        <ActiveTasksList tasks={tasks} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <CostSummaryCard costs={costs} budget={0} />
          <CostByAgentChart costs={costs} />
        </div>

        {activeWorkflows.length > 0 && (
          <div className="rounded-xl border border-border bg-surface-secondary p-4">
            <h3 className="text-sm font-semibold text-content-secondary mb-3">
              {t('multi_workflow.active_workflows')}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {activeWorkflows.map((wf) => (
                <WorkflowCard
                  key={wf.id}
                  workflow={wf}
                  onPause={(id) => void handleWorkflowAction('pause', id)}
                  onComplete={(id) => void handleWorkflowAction('complete', id)}
                />
              ))}
            </div>
          </div>
        )}

        {recentIssues.length > 0 && (
          <div className="rounded-xl border border-border bg-surface-secondary p-4">
            <h3 className="text-sm font-semibold text-content-secondary mb-3">
              {t('dashboard.recent_issues')}
            </h3>
            <div className="flex flex-col">
              {recentIssues.map((issue) => (
                <IssueRow key={issue.id} issue={issue} onClick={() => {}} />
              ))}
            </div>
          </div>
        )}

        {activityEntries.length > 0 && (
          <div className="rounded-xl border border-border bg-surface-secondary p-4">
            <ActivityTimeline entries={activityEntries} />
          </div>
        )}
      </div>
    </PageContainer>
  );
}
