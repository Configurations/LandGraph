import { useTranslation } from 'react-i18next';

export type ProjectTab = 'issues' | 'deliverables' | 'workflow' | 'activity' | 'team' | 'dependencies' | 'automation';

interface ProjectTabsProps {
  activeTab: ProjectTab;
  onTabChange: (tab: ProjectTab) => void;
  showAutomation?: boolean;
  className?: string;
}

const BASE_TABS: ProjectTab[] = ['issues', 'deliverables', 'workflow', 'activity', 'team', 'dependencies'];

export function ProjectTabs({
  activeTab,
  onTabChange,
  showAutomation = false,
  className = '',
}: ProjectTabsProps): JSX.Element {
  const { t } = useTranslation();
  const tabs = showAutomation ? [...BASE_TABS, 'automation' as ProjectTab] : BASE_TABS;

  return (
    <div className={`flex gap-1 border-b border-border ${className}`}>
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onTabChange(tab)}
          className={[
            'px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
            activeTab === tab
              ? 'border-accent-blue text-accent-blue'
              : 'border-transparent text-content-tertiary hover:text-content-primary',
          ].join(' ')}
        >
          {t(`project_detail.tab_${tab}`)}
        </button>
      ))}
    </div>
  );
}
