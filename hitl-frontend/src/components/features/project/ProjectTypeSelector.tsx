import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { Spinner } from '../../ui/Spinner';
import { ProjectTypeCard } from './ProjectTypeCard';
import * as projectTypesApi from '../../../api/projectTypes';
import type { ProjectTypeResponse } from '../../../api/types';

interface ProjectTypeSelectorProps {
  teamId: string;
  selectedTypeId: string | null;
  onSelect: (typeId: string | null) => void;
  className?: string;
}

export function ProjectTypeSelector({
  teamId,
  selectedTypeId,
  onSelect,
  className = '',
}: ProjectTypeSelectorProps): JSX.Element {
  const { t } = useTranslation();
  const [types, setTypes] = useState<ProjectTypeResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!teamId) return;
    setLoading(true);
    projectTypesApi
      .listProjectTypes(teamId)
      .then(setTypes)
      .catch(() => setTypes([]))
      .finally(() => setLoading(false));
  }, [teamId]);

  if (loading) {
    return (
      <div className={`flex justify-center py-8 ${className}`}>
        <Spinner />
      </div>
    );
  }

  if (types.length === 0) {
    return (
      <div className={`text-center py-8 ${className}`}>
        <p className="text-sm text-content-tertiary">{t('project_type.no_types')}</p>
        <Button variant="ghost" size="sm" onClick={() => onSelect(null)} className="mt-3">
          {t('project_type.skip')}
        </Button>
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      <h3 className="text-sm font-semibold text-content-secondary">
        {t('project_type.select_type')}
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {types.map((pt) => (
          <ProjectTypeCard
            key={pt.id}
            projectType={pt}
            selected={selectedTypeId === pt.id}
            onSelect={onSelect}
          />
        ))}
      </div>
      <Button variant="ghost" size="sm" onClick={() => onSelect(null)} className="self-start">
        {t('project_type.skip')}
      </Button>
    </div>
  );
}
