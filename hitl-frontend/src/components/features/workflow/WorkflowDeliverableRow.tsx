import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { DeliverableRunStatus, PhaseDeliverable } from '../../../api/types';

interface WorkflowDeliverableRowProps {
  deliverable: PhaseDeliverable;
  className?: string;
}

const statusColor: Record<DeliverableRunStatus, 'blue' | 'green' | 'orange' | 'red'> = {
  pending: 'blue',
  produced: 'orange',
  approved: 'green',
  rejected: 'red',
};

const typeColor: Record<string, 'purple' | 'blue' | 'green' | 'orange'> = {
  document: 'purple',
  code: 'blue',
  design: 'green',
  config: 'orange',
};

export function WorkflowDeliverableRow({
  deliverable,
  className = '',
}: WorkflowDeliverableRowProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div
      className={[
        'flex items-center justify-between rounded-lg border border-border bg-surface-tertiary px-3 py-2',
        className,
      ].join(' ')}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-sm font-mono text-content-primary truncate">
          {deliverable.key}
        </span>
        <Badge size="sm" color={typeColor[deliverable.deliverable_type] ?? 'blue'}>
          {deliverable.deliverable_type}
        </Badge>
      </div>
      <Badge size="sm" color={statusColor[deliverable.status]}>
        {t(`workflow.deliverable_status_${deliverable.status}`)}
      </Badge>
    </div>
  );
}
