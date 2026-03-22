import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AnalysisChat } from './AnalysisChat';
import { Spinner } from '../../ui/Spinner';
import { useProjectStore } from '../../../stores/projectStore';
import { useTeamStore } from '../../../stores/teamStore';
import * as ragApi from '../../../api/rag';

interface WizardStepAnalysisProps {
  className?: string;
}

export function WizardStepAnalysis({ className = '' }: WizardStepAnalysisProps): JSX.Element {
  const { t } = useTranslation();
  const slug = useProjectStore((s) => s.wizardData.slug);
  const teamId = useProjectStore((s) => s.wizardData.teamId);
  const activeTeamId = useTeamStore((s) => s.activeTeamId);

  const [taskId, setTaskId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const launch = useCallback(async () => {
    if (!slug) return;
    const resolvedTeam = teamId || activeTeamId;
    if (!resolvedTeam) return;

    setStarting(true);
    setError(null);
    try {
      const result = await ragApi.startAnalysis(slug, resolvedTeam);
      setTaskId(result.task_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(false);
    }
  }, [slug, teamId, activeTeamId]);

  useEffect(() => {
    void launch();
  }, [launch]);

  return (
    <div className={`flex flex-col gap-4 max-w-2xl ${className}`}>
      <h3 className="text-sm font-semibold text-content-primary">{t('analysis.title')}</h3>

      {starting && (
        <div className="flex items-center gap-2 text-content-secondary">
          <Spinner size="sm" />
          <span className="text-sm">{t('analysis.starting')}</span>
        </div>
      )}

      {error && <p className="text-xs text-accent-red">{error}</p>}

      {slug && <AnalysisChat slug={slug} taskId={taskId} />}
    </div>
  );
}
