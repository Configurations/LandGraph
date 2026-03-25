import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Badge } from '../../ui/Badge';
import { Avatar } from '../../ui/Avatar';
import type { ProjectHealth, ProjectOverviewData } from '../../../api/types';

interface ProjectHeaderProps {
  projectName: string;
  slug: string;
  overview: ProjectOverviewData;
  className?: string;
}

const healthColor: Record<ProjectHealth, 'green' | 'orange' | 'red'> = {
  'on-track': 'green',
  'at-risk': 'orange',
  'off-track': 'red',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function ProjectHeader({
  projectName,
  slug,
  overview,
  className = '',
}: ProjectHeaderProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      <div className="flex items-center gap-2 text-xs text-content-tertiary">
        <Link to="/projects" className="hover:text-content-primary transition-colors">
          {t('project.projects')}
        </Link>
        <span>/</span>
        <span className="text-content-primary">{projectName}</span>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-content-primary">{projectName}</h1>
          <Badge variant="status" color={healthColor[overview.health]}>
            {t(`project_detail.health_${overview.health}`)}
          </Badge>
        </div>
        <span className="text-xs font-mono text-content-quaternary">{slug}</span>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs text-content-tertiary">
        {overview.lead && (
          <div className="flex items-center gap-1.5">
            <span>{t('project_detail.lead')}:</span>
            <Avatar name={overview.lead} size="sm" />
            <span className="text-content-secondary">{overview.lead}</span>
          </div>
        )}
        <span>{formatDate(overview.start_date)}{overview.end_date ? ` - ${formatDate(overview.end_date)}` : ''}</span>
        <div className="flex items-center gap-1">
          {(overview.members ?? []).slice(0, 5).map((m) => (
            <Avatar key={m} name={m} size="sm" />
          ))}
          {(overview.members ?? []).length > 5 && (
            <span className="text-content-quaternary">+{(overview.members ?? []).length - 5}</span>
          )}
        </div>
        <span>{t('project_detail.cost')}: ${overview.total_cost.toFixed(2)}</span>
      </div>
    </div>
  );
}
