import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { PageContainer } from '../components/layout/PageContainer';
import { WizardShell } from '../components/features/project/WizardShell';
import { useProjectStore } from '../stores/projectStore';

export function ProjectWizardPage(): JSX.Element {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const resumeSlug = searchParams.get('resume');
  const resetWizard = useProjectStore((s) => s.resetWizard);

  useEffect(() => {
    // Don't reset if resuming an existing wizard
    if (!resumeSlug) {
      resetWizard();
    }
  }, [resetWizard, resumeSlug]);

  return (
    <PageContainer className="flex flex-col h-[calc(100vh-4rem)]">
      <h2 className="text-xl font-semibold mb-4 flex-shrink-0">
        {resumeSlug ? t('project.continue_setup') : t('project.new_project')}
      </h2>
      <WizardShell className="flex-1 min-h-0" />
    </PageContainer>
  );
}
