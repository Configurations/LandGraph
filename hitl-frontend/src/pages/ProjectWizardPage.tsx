import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { WizardShell } from '../components/features/project/WizardShell';
import { useProjectStore } from '../stores/projectStore';

export function ProjectWizardPage(): JSX.Element {
  const { t } = useTranslation();
  const resetWizard = useProjectStore((s) => s.resetWizard);

  useEffect(() => {
    resetWizard();
  }, [resetWizard]);

  return (
    <PageContainer>
      <h2 className="text-xl font-semibold mb-6">{t('project.new_project')}</h2>
      <WizardShell />
    </PageContainer>
  );
}
