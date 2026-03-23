import { useTranslation } from 'react-i18next';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import type { QuestionResponse } from '../../../api/types';

interface QuestionCardProps {
  question: QuestionResponse;
  onClick?: () => void;
  onApprove?: () => void;
  onReject?: () => void;
  className?: string;
}

const statusColorMap: Record<string, 'orange' | 'green' | 'red' | 'yellow'> = {
  pending: 'orange',
  answered: 'green',
  timeout: 'red',
  cancelled: 'yellow',
};

function useRelativeTime(dateStr: string): string {
  const { t } = useTranslation();
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMin / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMin < 1) return t('time.just_now');
  if (diffMin < 60) return t('time.minutes_ago', { count: diffMin });
  if (diffHours < 24) return t('time.hours_ago', { count: diffHours });
  return t('time.days_ago', { count: diffDays });
}

export function QuestionCard({
  question,
  onClick,
  onApprove,
  onReject,
  className = '',
}: QuestionCardProps): JSX.Element {
  const { t } = useTranslation();
  const relativeTime = useRelativeTime(question.created_at);
  const isPending = question.status === 'pending';
  const isApproval = question.request_type === 'approval';
  const statusColor = statusColorMap[question.status] ?? 'blue';

  return (
    <Card
      variant="interactive"
      onClick={onClick}
      className={`${isPending ? 'border-l-2 border-l-accent-orange' : ''} ${className}`}
    >
      <div className="flex items-start gap-3">
        <Avatar name={question.agent_id} size="md" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm">{question.agent_id}</span>
            <Badge color={statusColor} size="sm">
              {t(`hitl.${question.status}`)}
            </Badge>
            {isPending && (
              <span className="h-2 w-2 rounded-full bg-accent-orange animate-pulse" />
            )}
          </div>
          <p className="mt-1 text-sm text-content-secondary line-clamp-2">
            {question.prompt}
          </p>
          <div className="mt-2 flex items-center gap-3 text-xs text-content-tertiary">
            <span>{relativeTime}</span>
            <Badge color="purple" size="sm" variant="tag">
              {question.team_id}
            </Badge>
            <Badge color="blue" size="sm" variant="tag">
              {question.channel}
            </Badge>
          </div>
        </div>
      </div>
      {isPending && isApproval && (onApprove || onReject) && (
        <div className="mt-3 flex gap-2 justify-end">
          {onApprove && (
            <Button size="sm" variant="primary" onClick={(e) => { e.stopPropagation(); onApprove(); }}>
              {t('hitl.approve')}
            </Button>
          )}
          {onReject && (
            <Button size="sm" variant="danger" onClick={(e) => { e.stopPropagation(); onReject(); }}>
              {t('hitl.reject')}
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}
