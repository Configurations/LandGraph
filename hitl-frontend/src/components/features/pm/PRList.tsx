import { useTranslation } from 'react-i18next';
import { PRRow } from './PRRow';
import { Spinner } from '../../ui/Spinner';
import { EmptyState } from '../../ui/EmptyState';
import type { PRResponse, PRStatus } from '../../../api/types';

interface PRListProps {
  prs: PRResponse[];
  loading: boolean;
  statusFilter: PRStatus | '';
  onFilterChange: (status: PRStatus | '') => void;
  onSelect: (id: string) => void;
  className?: string;
}

type TabKey = '' | 'open' | 'approved' | 'draft' | 'merged';

const TABS: TabKey[] = ['', 'open', 'approved', 'draft', 'merged'];

function tabLabelKey(tab: TabKey): string {
  if (tab === '') return 'pr.tab_all';
  return `pr.tab_${tab}`;
}

function filterPRs(prs: PRResponse[], tab: PRStatus | ''): PRResponse[] {
  if (tab === '') return prs;
  if (tab === 'open') return prs.filter((p) => p.status === 'open' || p.status === 'changes_requested');
  return prs.filter((p) => p.status === tab);
}

export function PRList({
  prs,
  loading,
  statusFilter,
  onFilterChange,
  onSelect,
  className = '',
}: PRListProps): JSX.Element {
  const { t } = useTranslation();
  const filtered = filterPRs(prs, statusFilter);

  if (loading) {
    return (
      <div className={`flex justify-center py-12 ${className}`}>
        <Spinner />
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex gap-1 border-b border-border pb-2">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => onFilterChange(tab as PRStatus | '')}
            className={[
              'px-3 py-1.5 text-xs font-medium rounded-md transition-colors',
              statusFilter === tab
                ? 'bg-accent-blue/15 text-accent-blue'
                : 'text-content-tertiary hover:text-content-primary hover:bg-surface-hover',
            ].join(' ')}
          >
            {t(tabLabelKey(tab))}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <EmptyState titleKey="pr.no_prs" />
      ) : (
        filtered.map((pr) => (
          <PRRow key={pr.id} pr={pr} onClick={() => onSelect(pr.id)} />
        ))
      )}
    </div>
  );
}
