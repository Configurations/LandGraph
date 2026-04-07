import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import { RevisionHistory } from './RevisionHistory';
import * as deliverablesApi from '../../../api/deliverables';
import type { DeliverableWithContent } from '../../../api/types';

interface Props {
  deliverable: DeliverableWithContent;
  onRefresh: () => void;
}

type Mode = 'read' | 'edit' | 'comment';

const STATUS_COLORS: Record<string, string> = {
  pending: 'text-content-tertiary',
  running: 'text-accent-blue',
  review: 'text-accent-orange',
  revision: 'text-accent-blue',
  approved: 'text-accent-green',
  rejected: 'text-accent-red',
};

export function DeliverablePanel({ deliverable, onRefresh }: Props): JSX.Element {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>('read');
  const [editContent, setEditContent] = useState(deliverable.content);
  const [comment, setComment] = useState('');
  const [saving, setSaving] = useState(false);

  const handleValidate = useCallback(async () => {
    setSaving(true);
    try {
      await deliverablesApi.validateDeliverable(String(deliverable.id), 'approved');
      onRefresh();
    } finally {
      setSaving(false);
    }
  }, [deliverable.id, onRefresh]);

  const handleSaveEdit = useCallback(async () => {
    setSaving(true);
    try {
      await deliverablesApi.updateContent(String(deliverable.id), editContent);
      setMode('read');
      onRefresh();
    } finally {
      setSaving(false);
    }
  }, [deliverable.id, editContent, onRefresh]);

  const handleRevise = useCallback(async () => {
    if (!comment.trim()) return;
    setSaving(true);
    try {
      await deliverablesApi.reviseDeliverable(deliverable.id, comment);
      setComment('');
      setMode('read');
      onRefresh();
    } finally {
      setSaving(false);
    }
  }, [deliverable.id, comment, onRefresh]);

  const statusColor = STATUS_COLORS[deliverable.status] ?? '';
  const canAct = ['review', 'approved', 'rejected'].includes(deliverable.status);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border flex-shrink-0">
        <div>
          <span className="font-semibold text-sm">{deliverable.key}</span>
          <span className="text-xs text-content-tertiary ml-2">{deliverable.agent_name || deliverable.agent_id}</span>
          <span className={`text-xs font-medium ml-2 ${statusColor}`}>{deliverable.status}</span>
          {deliverable.version > 1 && <span className="text-xs text-content-tertiary ml-1">v{deliverable.version}</span>}
        </div>
        <div className="flex gap-1.5">
          {canAct && deliverable.status !== 'approved' && (
            <Button size="sm" onClick={() => void handleValidate()} loading={saving}>{t('workflow.validate')}</Button>
          )}
          {canAct && (
            <Button size="sm" variant="secondary" onClick={() => setMode(mode === 'comment' ? 'read' : 'comment')}>
              {t('workflow.comment')}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => { setEditContent(deliverable.content); setMode(mode === 'edit' ? 'read' : 'edit'); }}>
            {mode === 'edit' ? t('common.cancel') : t('workflow.edit')}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {mode === 'edit' ? (
          <div className="flex flex-col gap-2 h-full">
            <textarea
              className="flex-1 w-full rounded border border-border bg-surface-primary px-3 py-2 text-sm font-mono min-h-[300px]"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
            />
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setMode('read')}>{t('common.cancel')}</Button>
              <Button size="sm" onClick={() => void handleSaveEdit()} loading={saving}>{t('common.save')}</Button>
            </div>
          </div>
        ) : (
          <>
            {deliverable.content ? (
              <MarkdownRenderer content={deliverable.content} />
            ) : (
              <p className="text-sm text-content-tertiary italic">{t('workflow.no_content')}</p>
            )}
          </>
        )}

        {mode === 'comment' && (
          <div className="mt-4 border-t border-border pt-3">
            <textarea
              rows={3}
              className="w-full rounded border border-border bg-surface-primary px-3 py-2 text-sm"
              placeholder={t('workflow.comment_placeholder')}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
            <div className="flex justify-end gap-2 mt-2">
              <Button size="sm" variant="ghost" onClick={() => setMode('read')}>{t('common.cancel')}</Button>
              <Button size="sm" onClick={() => void handleRevise()} loading={saving} disabled={!comment.trim()}>
                {t('workflow.send_revision')}
              </Button>
            </div>
          </div>
        )}

        <RevisionHistory artifactId={deliverable.id} version={deliverable.version} />
      </div>
    </div>
  );
}
