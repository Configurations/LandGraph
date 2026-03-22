import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useProjectStore } from '../../../stores/projectStore';
import { useTeamStore } from '../../../stores/teamStore';
import * as projectsApi from '../../../api/projects';

interface WizardStepSetupProps {
  className?: string;
}

function toSlug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

export function WizardStepSetup({ className = '' }: WizardStepSetupProps): JSX.Element {
  const { t } = useTranslation();
  const wizardData = useProjectStore((s) => s.wizardData);
  const updateWizardData = useProjectStore((s) => s.updateWizardData);
  const teams = useTeamStore((s) => s.teams);
  const activeTeamId = useTeamStore((s) => s.activeTeamId);

  const [slugStatus, setSlugStatus] = useState<'idle' | 'checking' | 'available' | 'exists'>('idle');

  useEffect(() => {
    if (!wizardData.teamId && activeTeamId) {
      updateWizardData({ teamId: activeTeamId });
    }
  }, [activeTeamId, wizardData.teamId, updateWizardData]);

  const handleNameChange = useCallback(
    (value: string) => {
      const slug = toSlug(value);
      updateWizardData({ name: value, slug });
      setSlugStatus('idle');
    },
    [updateWizardData],
  );

  const checkSlug = useCallback(async () => {
    if (!wizardData.slug) return;
    setSlugStatus('checking');
    try {
      const result = await projectsApi.checkSlug(wizardData.slug);
      setSlugStatus(result.available ? 'available' : 'exists');
    } catch {
      setSlugStatus('exists');
    }
  }, [wizardData.slug]);

  useEffect(() => {
    if (!wizardData.slug) return;
    const timer = setTimeout(() => void checkSlug(), 500);
    return () => clearTimeout(timer);
  }, [wizardData.slug, checkSlug]);

  return (
    <div className={`flex flex-col gap-4 max-w-md ${className}`}>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-secondary">{t('project.name')}</span>
        <input
          type="text"
          value={wizardData.name}
          onChange={(e) => handleNameChange(e.target.value)}
          className="rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:border-accent-blue focus:outline-none"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-secondary">{t('project.slug')}</span>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={wizardData.slug}
            onChange={(e) => { updateWizardData({ slug: toSlug(e.target.value) }); setSlugStatus('idle'); }}
            className="flex-1 rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm font-mono text-content-primary focus:border-accent-blue focus:outline-none"
          />
          {slugStatus === 'checking' && <span className="text-xs text-content-tertiary">{t('project.slug_checking')}</span>}
          {slugStatus === 'available' && <span className="text-xs text-accent-green">{t('project.slug_available')}</span>}
          {slugStatus === 'exists' && <span className="text-xs text-accent-red">{t('project.slug_exists')}</span>}
        </div>
      </label>

      {teams.length > 1 && (
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium text-content-secondary">{t('nav.teams')}</span>
          <select
            value={wizardData.teamId}
            onChange={(e) => updateWizardData({ teamId: e.target.value })}
            className="rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary focus:border-accent-blue focus:outline-none"
          >
            {teams.map((team) => (
              <option key={team.id} value={team.id}>{team.name}</option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
