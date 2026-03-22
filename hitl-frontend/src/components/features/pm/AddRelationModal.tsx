import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../../ui/Modal';
import { Input } from '../../ui/Input';
import { Select } from '../../ui/Select';
import { Button } from '../../ui/Button';
import type { RelationCreatePayload, RelationType } from '../../../api/types';

interface AddRelationModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (payload: RelationCreatePayload) => void;
  sourceIssueId: string;
  className?: string;
}

const RELATION_TYPES: RelationType[] = ['blocks', 'relates_to', 'parent_of', 'duplicates'];

export function AddRelationModal({
  open,
  onClose,
  onCreated,
  sourceIssueId,
  className = '',
}: AddRelationModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [type, setType] = useState<RelationType>('blocks');
  const [targetId, setTargetId] = useState('');
  const [reason, setReason] = useState('');

  const reset = () => {
    setType('blocks');
    setTargetId('');
    setReason('');
  };

  const handleSubmit = () => {
    if (!targetId.trim()) return;
    onCreated({
      type,
      target_issue_id: targetId.trim(),
      reason: reason.trim() || undefined,
    });
    reset();
    onClose();
  };

  const typeOptions = RELATION_TYPES.map((rt) => ({
    value: rt,
    label: t(`relation.type_${rt}`),
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="relation.add_title"
      className={className}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSubmit} disabled={!targetId.trim()}>{t('common.save')}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="text-sm text-content-tertiary">
          {t('relation.from_issue', { id: sourceIssueId })}
        </div>
        <Select
          label={t('relation.type')}
          options={typeOptions}
          value={type}
          onChange={(e) => setType(e.target.value as RelationType)}
        />
        <Input
          label={t('relation.target_id')}
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          placeholder="ENG-042"
        />
        <Input
          label={t('relation.reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t('relation.reason_placeholder')}
        />
      </div>
    </Modal>
  );
}
