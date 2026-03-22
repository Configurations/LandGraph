import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { BranchInfo } from '../../../api/types';

interface BranchListProps {
  branches: BranchInfo[];
  onSelect: (name: string) => void;
  className?: string;
}

export function BranchList({
  branches,
  onSelect,
  className = '',
}: BranchListProps): JSX.Element {
  const { t } = useTranslation();

  if (branches.length === 0) {
    return (
      <div className={`text-center py-6 text-content-tertiary text-sm ${className}`}>
        {t('branch.no_branches')}
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      {branches.map((branch) => (
        <button
          key={branch.name}
          onClick={() => onSelect(branch.name)}
          className="flex items-center justify-between rounded-lg border border-border bg-surface-secondary px-3 py-2 hover:bg-surface-hover transition-colors text-left"
        >
          <div className="flex items-center gap-2 min-w-0">
            <svg className="h-4 w-4 text-content-tertiary shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span className="text-sm font-mono text-content-primary truncate">{branch.name}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {branch.ahead > 0 && (
              <Badge size="sm" color="green">+{branch.ahead}</Badge>
            )}
            {branch.behind > 0 && (
              <Badge size="sm" color="red">-{branch.behind}</Badge>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}
