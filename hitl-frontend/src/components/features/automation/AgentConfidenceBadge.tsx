import { useTranslation } from 'react-i18next';

interface AgentConfidenceBadgeProps {
  confidence: number;
  className?: string;
}

function getConfidenceColor(value: number): string {
  if (value >= 80) return 'bg-accent-green/15 text-accent-green';
  if (value >= 50) return 'bg-accent-orange/15 text-accent-orange';
  return 'bg-accent-red/15 text-accent-red';
}

export function AgentConfidenceBadge({
  confidence,
  className = '',
}: AgentConfidenceBadgeProps): JSX.Element {
  const { t } = useTranslation();
  const pct = Math.round(confidence);

  return (
    <span
      className={[
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        getConfidenceColor(pct),
        className,
      ].join(' ')}
      title={t('automation.confidence_tooltip', { value: pct })}
    >
      {t('automation.confidence_value', { value: pct })}
    </span>
  );
}
