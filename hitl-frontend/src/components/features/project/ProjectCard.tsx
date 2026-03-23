import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { GitStatusBadge } from './GitStatusBadge';
import type { ProjectResponse } from '../../../api/types';

interface ProjectCardProps {
  project: ProjectResponse;
  onDelete?: (slug: string) => Promise<void>;
  className?: string;
}

function relativeTime(iso: string, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return t('time.just_now');
  if (minutes < 60) return t('time.minutes_ago', { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('time.hours_ago', { count: hours });
  const days = Math.floor(hours / 24);
  return t('time.days_ago', { count: days });
}

export function ProjectCard({ project, onDelete, className = '' }: ProjectCardProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);

  const handleDelete = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onDelete) return;
    if (!window.confirm(t('project.confirm_delete'))) return;
    setDeleting(true);
    try {
      await onDelete(project.slug);
    } catch {
      setDeleting(false);
    }
  }, [onDelete, project.slug, t]);

  return (
    <button
      type="button"
      onClick={() => navigate(`/projects/${project.slug}`)}
      className={[
        'flex flex-col gap-3 rounded-lg border border-border bg-surface-secondary p-4 text-left',
        'transition-colors hover:bg-surface-hover hover:border-content-quaternary',
        className,
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-content-primary">{project.name}</h3>
          <p className="truncate text-xs font-mono text-content-tertiary">{project.slug}</p>
        </div>
        <GitStatusBadge connected={project.git_connected} repoExists={project.git_repo_exists} />
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <span className="rounded bg-surface-tertiary px-1.5 py-0.5 text-[10px] font-medium text-content-secondary">
          {project.team_id}
        </span>
        <span className="rounded bg-surface-tertiary px-1.5 py-0.5 text-[10px] font-medium text-content-secondary uppercase">
          {project.language}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-[10px] text-content-quaternary">
          {relativeTime(project.created_at, t)}
        </p>
        {onDelete && (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => void handleDelete(e)}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleDelete(e as unknown as React.MouseEvent); }}
            className={[
              'text-[10px] font-medium px-1.5 py-0.5 rounded transition-colors',
              deleting
                ? 'text-content-quaternary cursor-wait'
                : 'text-accent-red hover:bg-accent-red/10 cursor-pointer',
            ].join(' ')}
          >
            {deleting ? '...' : t('common.delete')}
          </span>
        )}
      </div>
    </button>
  );
}
