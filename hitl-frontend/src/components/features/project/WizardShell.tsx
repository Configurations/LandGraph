import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Stepper } from '../../ui/Stepper';
import { Button } from '../../ui/Button';
import { WizardStepSetup } from './WizardStepSetup';
import { WizardStepGit } from './WizardStepGit';
import { WizardStepCulture } from './WizardStepCulture';
import { ProjectTypeSelector } from './ProjectTypeSelector';
import { WizardStepDocuments } from './WizardStepDocuments';
import { WizardStepAnalysis } from './WizardStepAnalysis';
import { WizardStepSummary } from './WizardStepSummary';
import { useProjectStore } from '../../../stores/projectStore';
import { useTeamStore } from '../../../stores/teamStore';
import * as projectsApi from '../../../api/projects';
import * as projectTypesApi from '../../../api/projectTypes';
import * as wizardDataApi from '../../../api/wizardData';

interface WizardShellProps {
  className?: string;
}

const STEP_KEYS = [
  'wizard.step_setup',
  'wizard.step_git',
  'wizard.step_culture',
  'wizard.step_project_type',
  'wizard.step_documents',
  'wizard.step_analysis',
  'wizard.step_summary',
] as const;

const SKIPPABLE_STEPS = new Set([1, 3, 4, 5]);

export function WizardShell({ className = '' }: WizardShellProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const wizardStep = useProjectStore((s) => s.wizardStep);
  const setWizardStep = useProjectStore((s) => s.setWizardStep);
  const wizardData = useProjectStore((s) => s.wizardData);
  const resetWizard = useProjectStore((s) => s.resetWizard);
  const loadProjects = useProjectStore((s) => s.loadProjects);
  const teams = useTeamStore((s) => s.teams);
  const activeTeamId = useTeamStore((s) => s.activeTeamId);

  const [completed, setCompleted] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTypeId, setSelectedTypeId] = useState<string | null>(null);
  const [selectedWorkflowFilename, setSelectedWorkflowFilename] = useState<string>('');
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [selectedWorkflowIds, setSelectedWorkflowIds] = useState<string[]>([]);
  const updateWizardData = useProjectStore((s) => s.updateWizardData);

  // Restore step 3 selections from wizard data on resume
  useEffect(() => {
    if (!wizardData.slug) return;
    wizardDataApi.getWizardData(wizardData.slug).then((steps) => {
      const step3 = steps.find((s) => s.step_id === 3)?.data;
      if (step3) {
        if (step3.selectedTypeId) setSelectedTypeId(step3.selectedTypeId as string);
        if (step3.selectedChatId) setSelectedChatId(step3.selectedChatId as string);
        if (step3.selectedWorkflowIds) setSelectedWorkflowIds(step3.selectedWorkflowIds as string[]);
        if (step3.workflowFilename) setSelectedWorkflowFilename(step3.workflowFilename as string);
      }
    }).catch(() => {});
  }, [wizardData.slug]);

  const steps = useMemo(
    () => STEP_KEYS.map((key, idx) => ({ labelKey: key, completed: completed.has(idx) })),
    [completed],
  );

  const markComplete = useCallback((step: number) => {
    setCompleted((prev) => new Set([...prev, step]));
  }, []);

  const canAdvance = useMemo((): boolean => {
    if (wizardStep === 0) return wizardData.name.length > 0 && wizardData.slug.length > 0;
    if (wizardStep === 2) return wizardData.language.length > 0;
    return true;
  }, [wizardStep, wizardData]);

  const handleNext = useCallback(async () => {
    // Save wizard step data immediately at each step
    if (wizardStep === 0) {
      void wizardDataApi.saveWizardStep(wizardData.slug, 0, {
        name: wizardData.name,
        slug: wizardData.slug,
      });
    }

    if (wizardStep === 1) {
      void wizardDataApi.saveWizardStep(wizardData.slug, 1, {
        gitConfig: wizardData.gitConfig,
        gitBranch: wizardData.gitBranch,
      });
    }

    if (wizardStep === 2 && !completed.has(2)) {
      setCreating(true);
      setError(null);
      try {
        const teamId = wizardData.teamId || activeTeamId || teams[0]?.id || '';
        try {
          await projectsApi.createProject({
            name: wizardData.name,
            slug: wizardData.slug,
            language: wizardData.language,
            team_id: teamId,
            git_config: wizardData.gitConfig ?? undefined,
          });
          // Initialize git repo (clone existing or create new)
          if (wizardData.gitConfig) {
            await projectsApi.initGit(wizardData.slug, wizardData.gitConfig);
          }
          await loadProjects();
        } catch (createErr) {
          // 409 = slug already exists (resume mode) — skip creation
          const msg = createErr instanceof Error ? createErr.message : '';
          if (!msg.includes('slug_exists')) throw createErr;
        }
        markComplete(2);
        void wizardDataApi.saveWizardStep(wizardData.slug, 2, {
          language: wizardData.language,
          teamId: teamId,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setCreating(false);
        return;
      }
      setCreating(false);
    }

    if (wizardStep === 3 && selectedTypeId) {
      setCreating(true);
      setError(null);
      try {
        const firstWf = selectedWorkflowIds[0] || selectedWorkflowFilename;
        const result = await projectTypesApi.applyProjectType(
          wizardData.slug, selectedTypeId, firstWf,
        );
        updateWizardData({ orchestratorPrompt: result.orchestrator_prompt });
        void wizardDataApi.saveWizardStep(wizardData.slug, 3, {
          selectedTypeId,
          selectedChatId,
          selectedWorkflowIds,
          workflowFilename: selectedWorkflowIds[0] || selectedWorkflowFilename,
          orchestratorPrompt: result.orchestrator_prompt,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setCreating(false);
        return;
      }
      setCreating(false);
    }

    if (wizardStep === 4) {
      // Persist document step (best-effort)
      void wizardDataApi.saveWizardStep(wizardData.slug, 4, { completed: true });
    }

    markComplete(wizardStep);
    if (wizardStep < STEP_KEYS.length - 1) {
      setWizardStep(wizardStep + 1);
    } else {
      // Wizard complete — delete create-project.json
      void wizardDataApi.deleteWizardData(wizardData.slug);
      resetWizard();
      navigate('/projects');
    }
  }, [wizardStep, wizardData, completed, selectedTypeId, selectedChatId, selectedWorkflowIds, selectedWorkflowFilename, markComplete, setWizardStep, navigate, resetWizard, loadProjects, updateWizardData, activeTeamId, teams]);

  const handlePrevious = useCallback(() => {
    if (wizardStep > 0) setWizardStep(wizardStep - 1);
  }, [wizardStep, setWizardStep]);

  const handleSkip = useCallback(() => {
    if (wizardStep < STEP_KEYS.length - 1) {
      setWizardStep(wizardStep + 1);
    }
  }, [wizardStep, setWizardStep]);

  return (
    <div className={`flex flex-col ${className}`}>
      <Stepper steps={steps} activeStep={wizardStep} onStepClick={setWizardStep} />

      <div className="flex-1 overflow-y-auto min-h-0 py-4">
        {wizardStep === 0 && <WizardStepSetup />}
        {wizardStep === 1 && <WizardStepGit />}
        {wizardStep === 2 && <WizardStepCulture />}
        {wizardStep === 3 && (
          <ProjectTypeSelector
            selectedTypeId={selectedTypeId}
            selectedChatId={selectedChatId}
            selectedWorkflowIds={selectedWorkflowIds}
            onSelect={(typeId, chatId, workflowIds, workflowFilename) => {
              setSelectedTypeId(typeId);
              setSelectedChatId(chatId ?? null);
              setSelectedWorkflowIds(workflowIds ?? []);
              if (workflowFilename) setSelectedWorkflowFilename(workflowFilename);
            }}
          />
        )}
        {wizardStep === 4 && <WizardStepDocuments />}
        {wizardStep === 5 && <WizardStepAnalysis />}
        {wizardStep === 6 && <WizardStepSummary />}
      </div>

      {error && <p className="text-xs text-accent-red">{error}</p>}

      <div className="sticky bottom-0 flex items-center justify-between border-t border-border px-4 py-4 bg-surface-secondary">
        <Button variant="ghost" onClick={handlePrevious} disabled={wizardStep === 0}>
          {t('wizard.previous')}
        </Button>
        <div className="flex gap-3">
          {SKIPPABLE_STEPS.has(wizardStep) && (
            <Button variant="secondary" onClick={handleSkip}>
              {t('wizard.skip')}
            </Button>
          )}
          <Button onClick={() => void handleNext()} disabled={!canAdvance} loading={creating}>
            {wizardStep === 2 && !completed.has(2) ? t('project.create') : wizardStep === STEP_KEYS.length - 1 ? t('wizard.finalize') : t('wizard.next')}
          </Button>
        </div>
      </div>
    </div>
  );
}
