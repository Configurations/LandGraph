import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import type { DeliverableStatus } from '../../../api/types';

interface ValidationBadgeProps {
  status: DeliverableStatus;
  reviewer?: string | null;
  className?: string;
}

const statusColorMap: Record<DeliverableStatus, 'orange' | 'green' | 'red'> = {
  pending: 'orange',
  approved: 'green',
  rejected: 'red',
};

export function ValidationBadge({
  status,
  reviewer,
  className = '',
}: ValidationBadgeProps): JSX.Element {
  const { t } = useTranslation();
  const color = statusColorMap[status];
  const label = t(`deliverable.status_${status}`);
  const suffix = reviewer ? ` (${reviewer})` : '';

  return (
    <Badge variant="status" color={color} className={className}>
      {label}{suffix}
    </Badge>
  );
}
