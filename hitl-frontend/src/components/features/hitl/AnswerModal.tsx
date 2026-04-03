import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../../ui/Modal';
import { Button } from '../../ui/Button';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import { InteractiveQuestions } from './InteractiveQuestions';
import { parseQuestions, stripQuestionMarkers } from '../../../utils/questionParser';
import type { QuestionResponse } from '../../../api/types';

interface AnswerModalProps {
  question: QuestionResponse | null;
  open: boolean;
  onClose: () => void;
  onSubmit: (questionId: string, response: string, action: 'approve' | 'reject' | 'answer') => void;
  className?: string;
}

function formatContext(ctx: Record<string, unknown>): string {
  const labels: Record<string, string> = {
    type: 'Type',
    phase: 'Phase actuelle',
    next_phase: 'Phase suivante',
    project_slug: 'Projet',
    task_id: 'Tache',
    context: 'Contexte',
  };
  const lines: string[] = [];
  for (const [key, value] of Object.entries(ctx)) {
    if (!value || (typeof value === 'string' && !value.trim())) continue;
    const label = labels[key] || key;
    lines.push(`${label} : ${typeof value === 'string' ? value : JSON.stringify(value)}`);
  }
  return lines.join('\n');
}

export function AnswerModal({
  question,
  open,
  onClose,
  onSubmit,
  className = '',
}: AnswerModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);

  if (!question) return null;

  const isApproval = question.request_type === 'approval';
  const isPending = question.status === 'pending';
  const parsed = isPending && !isApproval ? parseQuestions(question.prompt) : null;
  const modalTitle = isApproval ? 'hitl.validation' : 'hitl.answer';

  const handleAction = async (action: 'approve' | 'reject' | 'answer') => {
    setLoading(true);
    try {
      onSubmit(question.id, response, action);
      setResponse('');
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const handleInteractiveSubmit = (text: string) => {
    onSubmit(question.id, text, 'answer');
    onClose();
  };

  const actions = isPending && !parsed ? (
    <>
      <Button variant="ghost" onClick={onClose}>
        {t('common.cancel')}
      </Button>
      {isApproval ? (
        <>
          <Button variant="danger" loading={loading} onClick={() => handleAction('reject')}>
            {t('hitl.reject')}
          </Button>
          <Button variant="primary" loading={loading} onClick={() => handleAction('approve')}>
            {t('hitl.approve')}
          </Button>
        </>
      ) : (
        <Button variant="primary" loading={loading} onClick={() => handleAction('answer')}>
          {t('hitl.answer')}
        </Button>
      )}
    </>
  ) : undefined;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={modalTitle}
      actions={actions}
      className={`max-w-3xl ${className}`}
    >
      <div className="flex items-center gap-3 mb-4">
        <Avatar name={question.agent_id} imageUrl={question.agent_avatar_url} size="md" />
        <div>
          <p className="font-medium text-sm">{question.agent_id}</p>
          <Badge color="purple" size="sm">{question.team_id}</Badge>
        </div>
      </div>

      {parsed && isPending ? (
        <InteractiveQuestions
          parsed={parsed}
          onSubmit={handleInteractiveSubmit}
        />
      ) : (
        <>
          <div className="rounded-lg bg-surface-tertiary p-3 mb-4">
            <p className="text-sm whitespace-pre-wrap">{stripQuestionMarkers(question.prompt)}</p>
          </div>

          {question.context && Object.keys(question.context).length > 0 && (
            <div className="rounded-lg bg-surface-primary border border-border p-3 mb-4 text-xs text-content-secondary whitespace-pre-wrap">
              {formatContext(question.context as Record<string, unknown>)}
            </div>
          )}

          {isPending && !isApproval && (
            <textarea
              value={response}
              onChange={(e) => setResponse(e.target.value)}
              placeholder={t('hitl.answer_placeholder')}
              rows={4}
              className="w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-sm resize-none focus:border-accent-blue focus:outline-none focus:ring-1 focus:ring-accent-blue"
            />
          )}

          {question.response && !isPending && (
            <div className="rounded-lg bg-surface-primary border border-border p-3">
              <p className="text-xs text-content-tertiary mb-1">{question.reviewer}</p>
              <p className="text-sm">{question.response}</p>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
