import { useTranslation } from 'react-i18next';
import { useProjectStore } from '../../../stores/projectStore';

interface WizardStepCultureProps {
  className?: string;
}

interface LanguageOption {
  value: string;
  label: string;
}

const LANGUAGES: LanguageOption[] = [
  { value: 'fr', label: 'Fran\u00e7ais' },
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Espa\u00f1ol' },
  { value: 'de', label: 'Deutsch' },
  { value: 'it', label: 'Italiano' },
  { value: 'pt', label: 'Portugu\u00eas' },
];

export function WizardStepCulture({ className = '' }: WizardStepCultureProps): JSX.Element {
  const { t } = useTranslation();
  const wizardData = useProjectStore((s) => s.wizardData);
  const updateWizardData = useProjectStore((s) => s.updateWizardData);

  return (
    <div className={`flex flex-col gap-4 max-w-md ${className}`}>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-secondary">{t('project.culture')}</span>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.value}
              type="button"
              onClick={() => updateWizardData({ language: lang.value })}
              className={[
                'rounded-lg border px-4 py-3 text-sm font-medium transition-colors',
                wizardData.language === lang.value
                  ? 'border-accent-blue bg-accent-blue/10 text-accent-blue'
                  : 'border-border bg-surface-primary text-content-secondary hover:border-content-quaternary',
              ].join(' ')}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </label>
    </div>
  );
}
