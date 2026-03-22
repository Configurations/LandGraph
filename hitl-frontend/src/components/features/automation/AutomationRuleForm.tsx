import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { Select } from '../../ui/Select';
import type { AutomationRule, AutomationRuleCreatePayload } from '../../../api/types';

interface AutomationRuleFormProps {
  open: boolean;
  initial: AutomationRule | null;
  workflowTypes: string[];
  deliverableTypes: string[];
  onSubmit: (payload: AutomationRuleCreatePayload) => void;
  onClose: () => void;
  className?: string;
}

export function AutomationRuleForm({
  open,
  initial,
  workflowTypes,
  deliverableTypes,
  onSubmit,
  onClose,
  className = '',
}: AutomationRuleFormProps): JSX.Element | null {
  const { t } = useTranslation();

  const [workflowType, setWorkflowType] = useState(initial?.workflow_type ?? workflowTypes[0] ?? '');
  const [deliverableType, setDeliverableType] = useState(initial?.deliverable_type ?? deliverableTypes[0] ?? '');
  const [autoApprove, setAutoApprove] = useState(initial?.auto_approve ?? false);
  const [threshold, setThreshold] = useState(initial?.confidence_threshold ?? 80);
  const [minHistory, setMinHistory] = useState(initial?.min_history ?? 5);

  const handleSubmit = useCallback(() => {
    onSubmit({
      workflow_type: workflowType,
      deliverable_type: deliverableType,
      auto_approve: autoApprove,
      confidence_threshold: threshold,
      min_history: minHistory,
    });
  }, [workflowType, deliverableType, autoApprove, threshold, minHistory, onSubmit]);

  if (!open) return null;

  const wfOptions = workflowTypes.map((v) => ({ value: v, label: v }));
  const delOptions = deliverableTypes.map((v) => ({ value: v, label: v }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        className={[
          'w-full max-w-md rounded-xl border border-border bg-surface-primary p-6 shadow-xl',
          className,
        ].join(' ')}
      >
        <h3 className="text-base font-semibold text-content-primary mb-4">
          {initial ? t('automation.edit_rule') : t('automation.add_rule')}
        </h3>

        <div className="flex flex-col gap-4">
          <Select
            label={t('automation.workflow_type')}
            options={wfOptions}
            value={workflowType}
            onChange={(e) => setWorkflowType(e.target.value)}
          />
          <Select
            label={t('automation.deliverable_type')}
            options={delOptions}
            value={deliverableType}
            onChange={(e) => setDeliverableType(e.target.value)}
          />

          <label className="flex items-center gap-2 text-sm text-content-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={autoApprove}
              onChange={(e) => setAutoApprove(e.target.checked)}
              className="h-4 w-4 rounded border-border bg-surface-tertiary accent-accent-blue"
            />
            {t('automation.auto_approve_label')}
          </label>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-content-secondary">
              {t('automation.confidence_threshold')} ({threshold}%)
            </label>
            <input
              type="range"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full accent-accent-blue"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-content-secondary">
              {t('automation.min_history_label', { value: minHistory })}
            </label>
            <input
              type="number"
              min={0}
              max={100}
              value={minHistory}
              onChange={(e) => setMinHistory(Number(e.target.value))}
              className="w-20 rounded-lg border border-border bg-surface-tertiary px-2 py-1 text-sm text-content-primary"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button size="sm" onClick={handleSubmit}>
            {t('common.save')}
          </Button>
        </div>
      </div>
    </div>
  );
}
