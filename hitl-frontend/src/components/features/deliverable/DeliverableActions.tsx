import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import type { DeliverableStatus } from '../../../api/types';

interface DeliverableActionsProps {
  status: DeliverableStatus;
  onApprove: () => void;
  onReject: () => void;
  onRemark: () => void;
  onEdit: () => void;
  className?: string;
}

export function DeliverableActions({
  status,
  onApprove,
  onReject,
  onRemark,
  onEdit,
  className = '',
}: DeliverableActionsProps): JSX.Element {
  const { t } = useTranslation();
  const isPending = status === 'pending';

  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {isPending && (
        <>
          <Button size="sm" variant="primary" onClick={onApprove}>
            {t('deliverable.approve')}
          </Button>
          <Button size="sm" variant="danger" onClick={onReject}>
            {t('deliverable.reject')}
          </Button>
        </>
      )}
      <Button size="sm" variant="secondary" onClick={onRemark}>
        {t('deliverable.remark')}
      </Button>
      <Button size="sm" variant="ghost" onClick={onEdit}>
        {t('deliverable.edit')}
      </Button>
    </div>
  );
}
