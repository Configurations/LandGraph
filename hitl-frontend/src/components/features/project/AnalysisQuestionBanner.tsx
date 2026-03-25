import { useTranslation } from 'react-i18next';

interface AnalysisQuestionBannerProps {
  className?: string;
}

export function AnalysisQuestionBanner({ className = '' }: AnalysisQuestionBannerProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 rounded-t-lg bg-accent-orange/10 border border-accent-orange/30 text-xs text-accent-orange ${className}`}
    >
      <span className="h-2 w-2 rounded-full bg-accent-orange animate-pulse" />
      {t('analysis.waiting_input')}
    </div>
  );
}
