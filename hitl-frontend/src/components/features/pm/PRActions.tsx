import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import type { PRStatus } from '../../../api/types';

interface PRActionsProps {
  status: PRStatus;
  onApprove: () => void;
  onRequestChanges: () => void;
  onMerge: () => void;
  loading?: boolean;
  className?: string;
}

export function PRActions({
  status,
  onApprove,
  onRequestChanges,
  onMerge,
  loading = false,
  className = '',
}: PRActionsProps): JSX.Element {
  const { t } = useTranslation();
  const canReview = status === 'open' || status === 'changes_requested';
  const canMerge = status === 'approved';

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {canReview && (
        <>
          <Button variant="primary" size="sm" onClick={onApprove} loading={loading}>
            {t('pr.approve')}
          </Button>
          <Button variant="secondary" size="sm" onClick={onRequestChanges} loading={loading}>
            {t('pr.request_changes')}
          </Button>
        </>
      )}
      {canMerge && (
        <Button variant="primary" size="sm" onClick={onMerge} loading={loading}>
          {t('pr.merge')}
        </Button>
      )}
    </div>
  );
}
