import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Stepper } from '../../ui/Stepper';
import { Button } from '../../ui/Button';
import { WizardStepSetup } from './WizardStepSetup';
import { WizardStepGit } from './WizardStepGit';
import { WizardStepCulture } from './WizardStepCulture';
import { WizardStepDocuments } from './WizardStepDocuments';
import { WizardStepAnalysis } from './WizardStepAnalysis';
import { useProjectStore } from '../../../stores/projectStore';
import * as projectsApi from '../../../api/projects';

interface WizardShellProps {
  className?: string;
}

const STEP_KEYS = [
  'wizard.step_setup',
  'wizard.step_git',
  'wizard.step_culture',
  'wizard.step_documents',
  'wizard.step_analysis',
] as const;

const SKIPPABLE_STEPS = new Set([1, 3, 4]);

export function WizardShell({ className = '' }: WizardShellProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const wizardStep = useProjectStore((s) => s.wizardStep);
  const setWizardStep = useProjectStore((s) => s.setWizardStep);
  const wizardData = useProjectStore((s) => s.wizardData);
  const resetWizard = useProjectStore((s) => s.resetWizard);
  const loadProjects = useProjectStore((s) => s.loadProjects);

  const [completed, setCompleted] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    if (wizardStep === 2 && !completed.has(2)) {
      setCreating(true);
      setError(null);
      try {
        await projectsApi.createProject({
          name: wizardData.name,
          slug: wizardData.slug,
          language: wizardData.language,
          team_id: wizardData.teamId,
          git_config: wizardData.gitConfig ?? undefined,
        });
        markComplete(2);
        await loadProjects();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setCreating(false);
        return;
      }
      setCreating(false);
    }

    markComplete(wizardStep);
    if (wizardStep < STEP_KEYS.length - 1) {
      setWizardStep(wizardStep + 1);
    } else {
      resetWizard();
      navigate('/projects');
    }
  }, [wizardStep, wizardData, completed, markComplete, setWizardStep, navigate, resetWizard, loadProjects]);

  const handlePrevious = useCallback(() => {
    if (wizardStep > 0) setWizardStep(wizardStep - 1);
  }, [wizardStep, setWizardStep]);

  const handleSkip = useCallback(() => {
    if (wizardStep < STEP_KEYS.length - 1) {
      setWizardStep(wizardStep + 1);
    }
  }, [wizardStep, setWizardStep]);

  return (
    <div className={`flex flex-col gap-6 ${className}`}>
      <Stepper steps={steps} activeStep={wizardStep} onStepClick={setWizardStep} />

      <div className="min-h-[300px]">
        {wizardStep === 0 && <WizardStepSetup />}
        {wizardStep === 1 && <WizardStepGit />}
        {wizardStep === 2 && <WizardStepCulture />}
        {wizardStep === 3 && <WizardStepDocuments />}
        {wizardStep === 4 && <WizardStepAnalysis />}
      </div>

      {error && <p className="text-xs text-accent-red">{error}</p>}

      <div className="flex items-center justify-between border-t border-border pt-4">
        <Button variant="ghost" size="sm" onClick={handlePrevious} disabled={wizardStep === 0}>
          {t('wizard.previous')}
        </Button>
        <div className="flex gap-2">
          {SKIPPABLE_STEPS.has(wizardStep) && (
            <Button variant="secondary" size="sm" onClick={handleSkip}>
              {t('wizard.skip')}
            </Button>
          )}
          <Button size="sm" onClick={() => void handleNext()} disabled={!canAdvance} loading={creating}>
            {wizardStep === 2 && !completed.has(2) ? t('project.create') : t('wizard.next')}
          </Button>
        </div>
      </div>
    </div>
  );
}
