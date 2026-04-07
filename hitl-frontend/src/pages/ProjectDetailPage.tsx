import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { Spinner } from '../components/ui/Spinner';
import { ProjectHeader } from '../components/features/project/ProjectHeader';
import { ProjectTabs, type ProjectTab } from '../components/features/project/ProjectTabs';
import { ProjectOverview } from '../components/features/project/ProjectOverview';
import { ProjectTeamGrid } from '../components/features/project/ProjectTeamGrid';
import { DependencyGraphSimple } from '../components/features/project/DependencyGraphSimple';
import { WorkflowExecutionPanel } from '../components/features/workflow/WorkflowExecutionPanel';
import { AutomationRuleList } from '../components/features/automation/AutomationRuleList';
import { AutomationRuleForm } from '../components/features/automation/AutomationRuleForm';
import { AutomationStats as AutomationStatsPanel } from '../components/features/automation/AutomationStats';
import { IssueList } from '../components/features/pm/IssueList';
import { Button } from '../components/ui/Button';
import { useIssueStore } from '../stores/issueStore';
import { useAuthStore } from '../stores/authStore';
import { useProjectStore } from '../stores/projectStore';
import { apiFetch } from '../api/client';
import * as workflowApi from '../api/workflow';
import * as automationApi from '../api/automation';
import * as wizardDataApi from '../api/wizardData';
import type {
  AgentInfo,
  AutomationRule,
  AutomationRuleCreatePayload,
  AutomationStats,
  IssueResponse,
  ProjectOverviewData,
  ProjectWorkflowResponse,
  RelationType,
} from '../api/types';

interface SimpleRelation {
  sourceId: string;
  targetId: string;
  type: RelationType;
}

export function ProjectDetailPage(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { slug } = useParams<{ slug: string }>();
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin');
  const storeDeleteProject = useProjectStore((s) => s.deleteProject);
  const projects = useProjectStore((s) => s.projects);
  const updateWizardData = useProjectStore((s) => s.updateWizardData);
  const setWizardStep = useProjectStore((s) => s.setWizardStep);
  const [deleting, setDeleting] = useState(false);
  const [tab, setTab] = useState<ProjectTab>('issues');
  const [overview, setOverview] = useState<ProjectOverviewData | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [relations, setRelations] = useState<SimpleRelation[]>([]);
  const [projectWorkflows, setProjectWorkflows] = useState<ProjectWorkflowResponse[]>([]);
  const [automationRules, setAutomationRules] = useState<AutomationRule[]>([]);
  const [automationStats, setAutomationStats] = useState<AutomationStats | null>(null);
  const [ruleFormOpen, setRuleFormOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<AutomationRule | null>(null);
  const [loading, setLoading] = useState(true);
  const { issues, loadIssues, setFilters, setSelected } = useIssueStore();

  // Redirect to wizard if project creation is not finished
  useEffect(() => {
    if (!slug) return;
    const project = projects.find((p) => p.slug === slug);
    if (project?.wizard_pending) {
      // Load wizard data and restore state, then redirect
      void wizardDataApi.getWizardData(slug).then((steps) => {
        const step0 = steps.find((s) => s.step_id === 0)?.data;
        const step1 = steps.find((s) => s.step_id === 1)?.data;
        const step3 = steps.find((s) => s.step_id === 3)?.data;
        if (step0) {
          updateWizardData({
            name: (step0.name as string) ?? '',
            slug: (step0.slug as string) ?? '',
          });
        }
        if (step1) {
          updateWizardData({
            gitConfig: (step1.gitConfig as null) ?? null,
            gitBranch: (step1.gitBranch as string) ?? '',
          });
        }
        if (step3) {
          updateWizardData({
            orchestratorPrompt: (step3.orchestratorPrompt as string) ?? null,
          });
        }
        setWizardStep(2); // Resume at step 2 (culture — first post-creation step)
        navigate(`/projects/new?resume=${slug}`, { replace: true });
      });
      return;
    }
  }, [slug, projects, navigate, updateWizardData, setWizardStep]);

  useEffect(() => {
    if (!slug) return;
    const project = projects.find((p) => p.slug === slug);
    if (project?.wizard_pending) return; // skip loading — redirecting to wizard
    setLoading(true);
    const encodedSlug = encodeURIComponent(slug);
    Promise.all([
      apiFetch<ProjectOverviewData>(`/api/projects/${encodedSlug}/overview`),
      apiFetch<AgentInfo[]>(`/api/projects/${encodedSlug}/agents`),
      apiFetch<SimpleRelation[]>(`/api/projects/${encodedSlug}/relations`),
      workflowApi.listProjectWorkflows(slug).catch(() => [] as ProjectWorkflowResponse[]),
    ])
      .then(([ov, ag, rels, pws]) => {
        setOverview(ov);
        setAgents(ag);
        setRelations(rels);
        setProjectWorkflows(pws);
      })
      .finally(() => setLoading(false));
    setFilters({ projectId: slug });
    void loadIssues();
  }, [slug, loadIssues, setFilters]);

  const loadAutomation = useCallback(async () => {
    if (!slug) return;
    const [rules, stats] = await Promise.all([
      automationApi.listRules(slug).catch(() => [] as AutomationRule[]),
      automationApi.getStats(slug).catch(() => ({ total_decisions: 0, auto_approved: 0, manual_reviewed: 0, rejected: 0 })),
    ]);
    setAutomationRules(rules);
    setAutomationStats(stats);
  }, [slug]);

  useEffect(() => {
    if (tab === 'automation') void loadAutomation();
  }, [tab, loadAutomation]);

  const handleToggleRule = useCallback(async (ruleId: string, enabled: boolean) => {
    if (!slug) return;
    await automationApi.updateRule(slug, ruleId, { enabled });
    void loadAutomation();
  }, [slug, loadAutomation]);

  const handleDeleteRule = useCallback(async (ruleId: string) => {
    if (!slug) return;
    await automationApi.deleteRule(slug, ruleId);
    void loadAutomation();
  }, [slug, loadAutomation]);

  const handleSubmitRule = useCallback(async (payload: AutomationRuleCreatePayload) => {
    if (!slug) return;
    if (editingRule) {
      await automationApi.updateRule(slug, editingRule.id, payload);
    } else {
      await automationApi.createRule(slug, payload);
    }
    setRuleFormOpen(false);
    setEditingRule(null);
    void loadAutomation();
  }, [slug, editingRule, loadAutomation]);

  const handleDeleteProject = useCallback(async () => {
    if (!slug) return;
    if (!window.confirm(t('project.confirm_delete'))) return;
    setDeleting(true);
    try {
      await storeDeleteProject(slug);
      navigate('/projects');
    } catch {
      setDeleting(false);
    }
  }, [slug, storeDeleteProject, navigate, t]);

  if (loading || !overview) {
    return (
      <PageContainer className="flex justify-center py-12">
        <Spinner />
      </PageContainer>
    );
  }

  const blockedIssues: IssueResponse[] = issues.filter((i) => i.is_blocked);
  const workflowTypes = [...new Set(projectWorkflows.map((w) => w.workflow_type))];
  const deliverableTypes = [...new Set(automationRules.map((r) => r.deliverable_type))];

  return (
    <PageContainer>
      <div className="flex items-start justify-between gap-4">
        <ProjectHeader projectName={slug ?? ''} slug={slug ?? ''} overview={overview} className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void handleDeleteProject()}
          loading={deleting}
          className="text-accent-red hover:bg-accent-red/10 shrink-0 mt-6"
        >
          {t('project.delete_project')}
        </Button>
      </div>
      <ProjectOverview overview={overview} className="mt-4" />
      <ProjectTabs activeTab={tab} onTabChange={setTab} showAutomation={isAdmin} className="mt-6" />

      <div className="mt-4">
        {tab === 'issues' && (
          <IssueList issues={issues} loading={false} onSelect={setSelected} groupBy="status" />
        )}
        {tab === 'workflow' && (
          <WorkflowExecutionPanel
            slug={slug!}
            workflows={projectWorkflows}
            onRefreshWorkflows={() => workflowApi.listProjectWorkflows(slug!).then(setProjectWorkflows)}
          />
        )}
        {tab === 'team' && (
          <ProjectTeamGrid agents={agents} members={overview.members} />
        )}
        {tab === 'dependencies' && (
          <DependencyGraphSimple issues={blockedIssues} relations={relations} />
        )}
        {tab === 'deliverables' && (
          <p className="text-sm text-content-tertiary">{t('project_detail.see_deliverables')}</p>
        )}
        {tab === 'activity' && (
          <p className="text-sm text-content-tertiary">{t('project_detail.see_activity')}</p>
        )}
        {tab === 'automation' && (
          <div className="flex flex-col gap-4">
            {automationStats && <AutomationStatsPanel stats={automationStats} />}
            <AutomationRuleList
              rules={automationRules}
              onToggle={(id, en) => void handleToggleRule(id, en)}
              onEdit={(rule) => { setEditingRule(rule); setRuleFormOpen(true); }}
              onDelete={(id) => void handleDeleteRule(id)}
              onAdd={() => { setEditingRule(null); setRuleFormOpen(true); }}
            />
            <AutomationRuleForm
              open={ruleFormOpen}
              initial={editingRule}
              workflowTypes={workflowTypes.length > 0 ? workflowTypes : ['default']}
              deliverableTypes={deliverableTypes.length > 0 ? deliverableTypes : ['document', 'code', 'design']}
              onSubmit={(p) => void handleSubmitRule(p)}
              onClose={() => { setRuleFormOpen(false); setEditingRule(null); }}
            />
          </div>
        )}
      </div>
    </PageContainer>
  );
}
