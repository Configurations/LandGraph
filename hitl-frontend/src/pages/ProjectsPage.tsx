import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { ProjectCard } from '../components/features/project/ProjectCard';
import { useProjectStore } from '../stores/projectStore';
import { useTeamStore } from '../stores/teamStore';

export function ProjectsPage(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const projects = useProjectStore((s) => s.projects);
  const loading = useProjectStore((s) => s.loading);
  const loadProjects = useProjectStore((s) => s.loadProjects);
  const activeTeamId = useTeamStore((s) => s.activeTeamId);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const filtered = useMemo(
    () => activeTeamId ? projects.filter((p) => p.team_id === activeTeamId) : projects,
    [projects, activeTeamId],
  );

  return (
    <PageContainer>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <h2 className="text-xl font-semibold">{t('project.projects')}</h2>
        <Button size="sm" onClick={() => navigate('/projects/new')}>
          + {t('project.new_project')}
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <p className="text-sm font-medium text-content-secondary">{t('project.no_projects')}</p>
          <p className="text-xs text-content-quaternary">{t('project.no_projects_desc')}</p>
          <Button size="sm" onClick={() => navigate('/projects/new')}>
            + {t('project.new_project')}
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </PageContainer>
  );
}
