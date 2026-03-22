import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { Badge } from '../../ui/Badge';
import type { AutomationRule } from '../../../api/types';

interface AutomationRuleListProps {
  rules: AutomationRule[];
  onToggle: (ruleId: string, enabled: boolean) => void;
  onEdit: (rule: AutomationRule) => void;
  onDelete: (ruleId: string) => void;
  onAdd: () => void;
  className?: string;
}

export function AutomationRuleList({
  rules,
  onToggle,
  onEdit,
  onDelete,
  onAdd,
  className = '',
}: AutomationRuleListProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-content-secondary">
          {t('automation.rules_title')}
        </h4>
        <Button variant="primary" size="sm" onClick={onAdd}>
          {t('automation.add_rule')}
        </Button>
      </div>

      {rules.length === 0 && (
        <p className="text-sm text-content-tertiary py-4">{t('automation.no_rules')}</p>
      )}

      <div className="flex flex-col gap-2">
        {rules.map((rule) => (
          <div
            key={rule.id}
            className="flex items-center gap-3 rounded-lg border border-border bg-surface-secondary p-3"
          >
            <button
              onClick={() => onToggle(rule.id, !rule.enabled)}
              className={[
                'relative h-5 w-9 rounded-full transition-colors',
                rule.enabled ? 'bg-accent-green' : 'bg-surface-tertiary',
              ].join(' ')}
              aria-label={t('automation.toggle_rule')}
            >
              <span
                className={[
                  'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
                  rule.enabled ? 'left-[18px]' : 'left-0.5',
                ].join(' ')}
              />
            </button>

            <div className="flex flex-col flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <Badge color="purple" size="sm">{rule.workflow_type}</Badge>
                <Badge color="blue" size="sm">{rule.deliverable_type}</Badge>
                {rule.auto_approve && (
                  <Badge color="green" size="sm">{t('automation.auto_approve')}</Badge>
                )}
              </div>
              <span className="text-xs text-content-tertiary mt-1">
                {t('automation.threshold_label', { value: rule.confidence_threshold })}
                {' / '}
                {t('automation.min_history_label', { value: rule.min_history })}
              </span>
            </div>

            <div className="flex gap-1">
              <Button variant="ghost" size="sm" onClick={() => onEdit(rule)}>
                {t('automation.edit')}
              </Button>
              <Button variant="danger" size="sm" onClick={() => onDelete(rule.id)}>
                {t('common.delete')}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
