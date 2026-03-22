import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import { Avatar } from '../../ui/Avatar';
import { ValidationBadge } from './ValidationBadge';
import { DeliverableActions } from './DeliverableActions';
import { MarkdownRenderer } from './MarkdownRenderer';
import { RemarkForm } from './RemarkForm';
import * as deliverablesApi from '../../../api/deliverables';
import type { DeliverableDetail as DeliverableDetailType, RemarkResponse } from '../../../api/types';

interface DeliverableDetailProps {
  deliverable: DeliverableDetailType;
  onValidate: (verdict: 'approved' | 'rejected', comment?: string) => void;
  onRemark: (comment: string) => void;
  className?: string;
}

export function DeliverableDetail({
  deliverable,
  onValidate,
  onRemark,
  className = '',
}: DeliverableDetailProps): JSX.Element {
  const { t } = useTranslation();
  const [remarks, setRemarks] = useState<RemarkResponse[]>([]);
  const [remarkLoading, setRemarkLoading] = useState(false);
  const [showRemarkForm, setShowRemarkForm] = useState(false);

  const loadRemarks = useCallback(async () => {
    try {
      const data = await deliverablesApi.listRemarks(deliverable.id);
      setRemarks(data);
    } catch {
      // handled by apiFetch
    }
  }, [deliverable.id]);

  useEffect(() => {
    void loadRemarks();
  }, [loadRemarks]);

  const handleRemark = async (comment: string) => {
    setRemarkLoading(true);
    try {
      onRemark(comment);
      await loadRemarks();
      setShowRemarkForm(false);
    } finally {
      setRemarkLoading(false);
    }
  };

  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      <div className="flex items-start gap-3">
        <Avatar name={deliverable.agent_id} size="md" />
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-content-primary">{deliverable.key}</h3>
          <div className="flex flex-wrap items-center gap-2 mt-1">
            <Badge size="sm" color="blue">{deliverable.phase}</Badge>
            <Badge size="sm" color="purple">{deliverable.deliverable_type}</Badge>
            <Badge size="sm" color="orange">{deliverable.category}</Badge>
            <ValidationBadge status={deliverable.status} reviewer={deliverable.reviewer} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-content-tertiary border border-border rounded-lg p-3">
        <div>
          <span className="font-medium text-content-secondary">{t('deliverable.task')}: </span>
          {deliverable.task_id}
        </div>
        <div>
          <span className="font-medium text-content-secondary">{t('deliverable.cost')}: </span>
          ${deliverable.cost_usd.toFixed(4)}
        </div>
        <div>
          <span className="font-medium text-content-secondary">{t('deliverable.agent')}: </span>
          {deliverable.agent_id}
        </div>
        <div>
          <span className="font-medium text-content-secondary">{t('deliverable.date')}: </span>
          {new Date(deliverable.created_at).toLocaleDateString()}
        </div>
      </div>

      <MarkdownRenderer content={deliverable.content} />

      <DeliverableActions
        status={deliverable.status}
        onApprove={() => onValidate('approved')}
        onReject={() => onValidate('rejected')}
        onRemark={() => setShowRemarkForm((v) => !v)}
        onEdit={() => { /* future: inline editing */ }}
      />

      {showRemarkForm && (
        <RemarkForm onSubmit={handleRemark} loading={remarkLoading} />
      )}

      {remarks.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-sm font-semibold text-content-secondary">
            {t('deliverable.remarks')} ({remarks.length})
          </h4>
          {remarks.map((r) => (
            <div key={r.id} className="rounded-lg border border-border bg-surface-tertiary p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-content-secondary">{r.reviewer}</span>
                <span className="text-[10px] text-content-quaternary">
                  {new Date(r.created_at).toLocaleDateString()}
                </span>
              </div>
              <p className="text-sm text-content-primary">{r.comment}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
