import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../../ui/Modal';
import { Button } from '../../ui/Button';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import type { QuestionResponse } from '../../../api/types';

interface AnswerModalProps {
  question: QuestionResponse | null;
  open: boolean;
  onClose: () => void;
  onSubmit: (questionId: string, response: string, action: 'approve' | 'reject' | 'answer') => void;
  className?: string;
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

  const isApproval = question.question_type === 'approval';
  const isPending = question.status === 'pending';

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

  const actions = isPending ? (
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
      title="hitl.answer"
      actions={actions}
      className={className}
    >
      <div className="flex items-center gap-3 mb-4">
        <Avatar name={question.agent_name} />
        <div>
          <p className="font-medium text-sm">{question.agent_name}</p>
          <Badge color="purple" size="sm">{question.team_id}</Badge>
        </div>
      </div>

      <div className="rounded-lg bg-surface-tertiary p-3 mb-4">
        <p className="text-sm whitespace-pre-wrap">{question.prompt}</p>
      </div>

      {question.context && (
        <details className="mb-4">
          <summary className="cursor-pointer text-xs text-content-tertiary hover:text-content-secondary">
            Context
          </summary>
          <pre className="mt-2 rounded-lg bg-surface-primary p-3 text-xs text-content-secondary font-mono overflow-x-auto">
            {question.context}
          </pre>
        </details>
      )}

      {isPending && (
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
    </Modal>
  );
}
