import { useTranslation } from 'react-i18next';
import { QuestionCard } from './QuestionCard';
import { EmptyState } from '../../ui/EmptyState';
import { Spinner } from '../../ui/Spinner';
import type { QuestionResponse } from '../../../api/types';

interface QuestionListProps {
  questions: QuestionResponse[];
  loading: boolean;
  emptyStateKey?: string;
  onQuestionClick?: (question: QuestionResponse) => void;
  onApprove?: (question: QuestionResponse) => void;
  onReject?: (question: QuestionResponse) => void;
  className?: string;
}

export function QuestionList({
  questions,
  loading,
  emptyStateKey = 'hitl.no_pending',
  onQuestionClick,
  onApprove,
  onReject,
  className = '',
}: QuestionListProps): JSX.Element {
  const { t } = useTranslation();

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <EmptyState
        titleKey={emptyStateKey}
        icon={
          <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
        }
        className={className}
      />
    );
  }

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      {questions.map((q) => (
        <QuestionCard
          key={q.id}
          question={q}
          onClick={() => onQuestionClick?.(q)}
          onApprove={onApprove ? () => onApprove(q) : undefined}
          onReject={onReject ? () => onReject(q) : undefined}
        />
      ))}
    </div>
  );
}
