import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { ProjectTypeResponse } from '../../../api/types';

interface ProjectTypeCardProps {
  projectType: ProjectTypeResponse;
  selected: boolean;
  onSelect: (id: string) => void;
  className?: string;
}

export function ProjectTypeCard({
  projectType,
  selected,
  onSelect,
  className = '',
}: ProjectTypeCardProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <button
      onClick={() => onSelect(projectType.id)}
      className={[
        'flex flex-col gap-2 rounded-xl border-2 p-4 text-left transition-all',
        'hover:border-accent-blue/60 hover:bg-surface-hover',
        selected
          ? 'border-accent-blue bg-accent-blue/5'
          : 'border-border bg-surface-secondary',
        className,
      ].join(' ')}
    >
      <h4 className="text-sm font-semibold text-content-primary">
        {projectType.name}
      </h4>
      <p className="text-xs text-content-tertiary line-clamp-2">
        {projectType.description}
      </p>
      <div className="flex items-center gap-2 mt-auto pt-2">
        <Badge color="purple" size="sm">
          {t('project_type.workflows_count', { count: projectType.workflows.length })}
        </Badge>
        <Badge color="blue" size="sm">
          {projectType.team}
        </Badge>
      </div>
    </button>
  );
}
