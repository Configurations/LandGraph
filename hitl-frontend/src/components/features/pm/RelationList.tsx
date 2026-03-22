import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { IssueStatusIcon } from './IssueStatusIcon';
import { Badge } from '../../ui/Badge';
import { Button } from '../../ui/Button';
import type { RelationResponse, RelationType } from '../../../api/types';

interface RelationListProps {
  relations: RelationResponse[];
  onDelete: (id: string) => void;
  className?: string;
}

const relationColor: Record<RelationType, 'red' | 'blue' | 'orange' | 'purple'> = {
  blocks: 'red',
  relates_to: 'blue',
  parent_of: 'orange',
  duplicates: 'purple',
};

export function RelationList({
  relations,
  onDelete,
  className = '',
}: RelationListProps): JSX.Element {
  const { t } = useTranslation();

  if (relations.length === 0) {
    return (
      <div className={`text-sm text-content-quaternary ${className}`}>
        {t('relation.no_relations')}
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <span className="text-sm font-medium text-content-secondary">
        {t('relation.relations')}
      </span>
      {relations.map((rel) => (
        <div
          key={rel.id}
          className="flex items-center gap-2 rounded-lg px-2 py-1.5 bg-surface-tertiary"
        >
          <Badge size="sm" color={relationColor[rel.type]}>
            {t(`relation.type_${rel.type}`)}
          </Badge>
          <Link
            to={`/issues?selected=${rel.issue_id}`}
            className="font-mono text-xs text-accent-blue hover:underline shrink-0"
          >
            {rel.issue_id}
          </Link>
          <IssueStatusIcon status={rel.issue_status} size={12} />
          <span className="flex-1 truncate text-sm text-content-secondary">
            {rel.issue_title}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(rel.id)}
            aria-label={t('common.delete')}
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </Button>
        </div>
      ))}
    </div>
  );
}
