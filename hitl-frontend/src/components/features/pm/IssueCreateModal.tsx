import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../../ui/Modal';
import { Input } from '../../ui/Input';
import { Select } from '../../ui/Select';
import { Button } from '../../ui/Button';
import type { IssueCreatePayload, IssuePriority, IssueStatus } from '../../../api/types';

interface IssueCreateModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (payload: IssueCreatePayload) => void;
  teamId: string;
  className?: string;
}

const STATUS_OPTIONS: IssueStatus[] = ['backlog', 'todo', 'in-progress', 'in-review', 'done'];
const PRIORITY_OPTIONS: IssuePriority[] = [1, 2, 3, 4];

export function IssueCreateModal({
  open,
  onClose,
  onCreated,
  className = '',
}: IssueCreateModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<IssuePriority>(3);
  const [status, setStatus] = useState<IssueStatus>('backlog');
  const [assignee, setAssignee] = useState('');
  const [tagsRaw, setTagsRaw] = useState('');

  const reset = () => {
    setTitle('');
    setDescription('');
    setPriority(3);
    setStatus('backlog');
    setAssignee('');
    setTagsRaw('');
  };

  const handleSubmit = () => {
    if (!title.trim()) return;
    const tags = tagsRaw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    onCreated({
      title: title.trim(),
      description: description.trim() || undefined,
      priority,
      status,
      assignee: assignee.trim() || undefined,
      tags: tags.length > 0 ? tags : undefined,
    });
    reset();
    onClose();
  };

  const statusOptions = STATUS_OPTIONS.map((s) => ({
    value: s,
    label: t(`issue.status_${s}`),
  }));

  const priorityOptions = PRIORITY_OPTIONS.map((p) => ({
    value: String(p),
    label: t('issue.priority_label', { level: p }),
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="issue.create_title"
      className={className}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSubmit} disabled={!title.trim()}>{t('common.save')}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label={t('issue.title')} value={title} onChange={(e) => setTitle(e.target.value)} />
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-content-secondary">{t('issue.description')}</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-sm text-content-primary min-h-[80px]"
            placeholder={t('issue.description_placeholder')}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Select label={t('issue.priority')} options={priorityOptions} value={String(priority)} onChange={(e) => setPriority(Number(e.target.value) as IssuePriority)} />
          <Select label={t('issue.status')} options={statusOptions} value={status} onChange={(e) => setStatus(e.target.value as IssueStatus)} />
        </div>
        <Input label={t('issue.assignee')} value={assignee} onChange={(e) => setAssignee(e.target.value)} />
        <Input label={t('issue.tags')} value={tagsRaw} onChange={(e) => setTagsRaw(e.target.value)} placeholder={t('issue.tags_placeholder')} />
      </div>
    </Modal>
  );
}
