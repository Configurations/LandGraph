import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BlockedBanner } from './BlockedBanner';
import { RelationList } from './RelationList';
import { Badge } from '../../ui/Badge';
import { Button } from '../../ui/Button';
import { Select } from '../../ui/Select';
import { Input } from '../../ui/Input';
import type { IssueDetail as IssueDetailType, IssuePriority, IssueStatus, IssueUpdatePayload } from '../../../api/types';

interface IssueDetailProps {
  issue: IssueDetailType;
  onUpdate: (data: IssueUpdatePayload) => void;
  onDelete: () => void;
  onAddRelation?: () => void;
  className?: string;
}

const STATUS_OPTIONS: IssueStatus[] = ['backlog', 'todo', 'in-progress', 'in-review', 'done'];
const PRIORITY_OPTIONS: IssuePriority[] = [1, 2, 3, 4];

export function IssueDetail({
  issue,
  onUpdate,
  onDelete,
  onAddRelation,
  className = '',
}: IssueDetailProps): JSX.Element {
  const { t } = useTranslation();
  const [editingDesc, setEditingDesc] = useState(false);
  const [desc, setDesc] = useState(issue.description);

  const blockedBy = issue.relations
    .filter((r) => r.type === 'blocks' && r.direction === 'incoming')
    .map((r) => ({ id: r.issue_id, title: r.issue_title }));

  const statusOptions = STATUS_OPTIONS.map((s) => ({
    value: s,
    label: t(`issue.status_${s}`),
  }));

  const priorityOptions = PRIORITY_OPTIONS.map((p) => ({
    value: String(p),
    label: t('issue.priority_label', { level: p }),
  }));

  const saveDescription = () => {
    onUpdate({ description: desc });
    setEditingDesc(false);
  };

  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      <h3 className="text-lg font-semibold text-content-primary">{issue.title}</h3>
      <span className="font-mono text-xs text-content-tertiary">{issue.id}</span>

      {blockedBy.length > 0 && <BlockedBanner blockedBy={blockedBy} />}

      <div className="grid grid-cols-2 gap-3">
        <Select
          label={t('issue.status')}
          options={statusOptions}
          value={issue.status}
          onChange={(e) => onUpdate({ status: e.target.value as IssueStatus })}
        />
        <Select
          label={t('issue.priority')}
          options={priorityOptions}
          value={String(issue.priority)}
          onChange={(e) => onUpdate({ priority: Number(e.target.value) as IssuePriority })}
        />
        <Input
          label={t('issue.assignee')}
          value={issue.assignee}
          onChange={(e) => onUpdate({ assignee: e.target.value })}
        />
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-content-secondary">{t('issue.team')}</span>
          <span className="text-sm text-content-primary">{issue.team_id}</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-content-secondary">{t('issue.phase')}</span>
          <span className="text-sm text-content-primary">{issue.phase}</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-content-secondary">{t('issue.created_at')}</span>
          <span className="text-sm text-content-tertiary">
            {new Date(issue.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {issue.tags.map((tag) => (
          <Badge key={tag} size="sm" color="purple">{tag}</Badge>
        ))}
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-content-secondary">{t('issue.description')}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => editingDesc ? saveDescription() : setEditingDesc(true)}
          >
            {editingDesc ? t('common.save') : t('deliverable.edit')}
          </Button>
        </div>
        {editingDesc ? (
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-sm text-content-primary min-h-[100px]"
          />
        ) : (
          <p className="text-sm text-content-secondary whitespace-pre-wrap">
            {issue.description || t('issue.no_description')}
          </p>
        )}
      </div>

      <RelationList relations={issue.relations} onDelete={() => {}} />

      {onAddRelation && (
        <Button variant="secondary" size="sm" onClick={onAddRelation}>
          {t('issue.add_relation')}
        </Button>
      )}

      <div className="border-t border-border pt-3">
        <Button variant="danger" size="sm" onClick={onDelete}>
          {t('common.delete')}
        </Button>
      </div>
    </div>
  );
}
