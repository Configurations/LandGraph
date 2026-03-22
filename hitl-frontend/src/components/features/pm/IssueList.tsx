import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { IssueRow } from './IssueRow';
import { Spinner } from '../../ui/Spinner';
import { EmptyState } from '../../ui/EmptyState';
import type { IssueGroupBy, IssueResponse } from '../../../api/types';

interface IssueListProps {
  issues: IssueResponse[];
  loading: boolean;
  onSelect: (id: string) => void;
  groupBy: IssueGroupBy;
  className?: string;
}

function getGroupKey(issue: IssueResponse, groupBy: IssueGroupBy): string {
  switch (groupBy) {
    case 'status':
      return issue.status;
    case 'team':
      return issue.team_id;
    case 'assignee':
      return issue.assignee || 'unassigned';
    case 'dependency':
      if (issue.is_blocked) return 'blocked';
      if (issue.blocking_count > 0) return 'blocking';
      return 'none';
  }
}

function groupIssues(
  issues: IssueResponse[],
  groupBy: IssueGroupBy,
): Map<string, IssueResponse[]> {
  const groups = new Map<string, IssueResponse[]>();
  for (const issue of issues) {
    const key = getGroupKey(issue, groupBy);
    const list = groups.get(key) ?? [];
    list.push(issue);
    groups.set(key, list);
  }
  return groups;
}

export function IssueList({
  issues,
  loading,
  onSelect,
  groupBy,
  className = '',
}: IssueListProps): JSX.Element {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    );
  }

  if (issues.length === 0) {
    return <EmptyState titleKey="issue.no_issues" />;
  }

  const groups = groupIssues(issues, groupBy);

  const toggleGroup = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      {Array.from(groups.entries()).map(([groupKey, groupIssues]) => (
        <div key={groupKey}>
          <button
            onClick={() => toggleGroup(groupKey)}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-content-tertiary hover:text-content-primary w-full text-left"
          >
            <svg
              className={`h-3 w-3 transition-transform ${collapsed.has(groupKey) ? '' : 'rotate-90'}`}
              fill="currentColor"
              viewBox="0 0 16 16"
            >
              <path d="M6 4l4 4-4 4V4z" />
            </svg>
            <span>{t(`issue.group_value_${groupKey}`, groupKey)}</span>
            <span className="text-content-quaternary">({groupIssues.length})</span>
          </button>
          {!collapsed.has(groupKey) &&
            groupIssues.map((issue) => (
              <IssueRow
                key={issue.id}
                issue={issue}
                onClick={() => onSelect(issue.id)}
              />
            ))}
        </div>
      ))}
    </div>
  );
}
