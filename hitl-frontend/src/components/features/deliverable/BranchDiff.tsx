import { useTranslation } from 'react-i18next';
import type { BranchDiffFile } from '../../../api/types';

interface BranchDiffProps {
  branch: string;
  files: BranchDiffFile[];
  className?: string;
}

const statusColors: Record<string, string> = {
  added: 'text-accent-green',
  modified: 'text-accent-orange',
  deleted: 'text-accent-red',
  renamed: 'text-accent-blue',
};

function DiffBar({ additions, deletions }: { additions: number; deletions: number }): JSX.Element {
  const total = additions + deletions;
  if (total === 0) return <span className="text-xs text-content-quaternary">0</span>;
  const maxBlocks = 5;
  const addBlocks = Math.max(1, Math.round((additions / total) * maxBlocks));
  const delBlocks = maxBlocks - addBlocks;

  return (
    <div className="flex items-center gap-0.5">
      <span className="text-xs text-content-tertiary mr-1">{total}</span>
      {Array.from({ length: addBlocks }).map((_, i) => (
        <span key={`a${i}`} className="inline-block h-2 w-2 rounded-sm bg-accent-green" />
      ))}
      {Array.from({ length: delBlocks }).map((_, i) => (
        <span key={`d${i}`} className="inline-block h-2 w-2 rounded-sm bg-accent-red" />
      ))}
    </div>
  );
}

export function BranchDiff({
  branch,
  files,
  className = '',
}: BranchDiffProps): JSX.Element {
  const { t } = useTranslation();

  if (files.length === 0) {
    return (
      <div className={`text-center py-6 text-content-tertiary text-sm ${className}`}>
        {t('branch.no_changes')}
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-mono text-content-secondary">{branch}</span>
        <span className="text-xs text-content-quaternary">
          {t('branch.files_changed', { count: files.length })}
        </span>
      </div>
      {files.map((file) => (
        <div
          key={file.path}
          className="flex items-center justify-between rounded-lg border border-border bg-surface-tertiary px-3 py-2"
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className={`text-xs font-medium ${statusColors[file.status] ?? 'text-content-tertiary'}`}>
              {file.status.charAt(0).toUpperCase()}
            </span>
            <span className="text-sm font-mono text-content-primary truncate">{file.path}</span>
          </div>
          <DiffBar additions={file.additions} deletions={file.deletions} />
        </div>
      ))}
    </div>
  );
}
