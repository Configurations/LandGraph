import { useTranslation } from 'react-i18next';
import { Card } from '../../ui/Card';
import type { IssueStatus, ProjectOverviewData } from '../../../api/types';

interface ProjectOverviewProps {
  overview: ProjectOverviewData;
  className?: string;
}

const STATUS_ORDER: IssueStatus[] = ['backlog', 'todo', 'in-progress', 'in-review', 'done'];

export function ProjectOverview({ overview, className = '' }: ProjectOverviewProps): JSX.Element {
  const { t } = useTranslation();
  const totalIssues = STATUS_ORDER.reduce(
    (sum, s) => sum + (overview.issues_by_status[s] ?? 0),
    0,
  );

  return (
    <div className={`grid grid-cols-2 lg:grid-cols-4 gap-3 ${className}`}>
      <Card>
        <p className="text-xs text-content-tertiary">{t('project_detail.issues_summary')}</p>
        <p className="text-2xl font-bold text-content-primary mt-1">{totalIssues}</p>
        <div className="flex gap-1 mt-2 flex-wrap">
          {STATUS_ORDER.map((s) => {
            const count = overview.issues_by_status[s] ?? 0;
            if (count === 0) return null;
            return (
              <span key={s} className="text-[10px] text-content-tertiary">
                {t(`issue.status_${s}`)}: {count}
              </span>
            );
          })}
        </div>
      </Card>

      <Card>
        <p className="text-xs text-content-tertiary">{t('project_detail.deliverables_count')}</p>
        <p className="text-2xl font-bold text-content-primary mt-1">
          {overview.deliverables_count}
        </p>
      </Card>

      <Card>
        <p className="text-xs text-content-tertiary">{t('project_detail.total_cost')}</p>
        <p className="text-2xl font-bold text-content-primary mt-1">
          ${overview.total_cost.toFixed(2)}
        </p>
      </Card>

      <Card>
        <p className="text-xs text-content-tertiary">{t('project_detail.current_phase')}</p>
        <p className="text-lg font-semibold text-accent-blue mt-1">
          {t(`workflow.phase_${overview.current_phase}`, { defaultValue: overview.current_phase })}
        </p>
      </Card>
    </div>
  );
}
