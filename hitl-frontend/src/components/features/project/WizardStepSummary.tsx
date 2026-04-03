import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import { Spinner } from '../../ui/Spinner';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import { useProjectStore } from '../../../stores/projectStore';
import { apiFetch } from '../../../api/client';

interface SummaryData {
  project_name: string;
  summary: string;
  facts: Array<{ name: string; type: string; observations: string[] }>;
  rag_summary: string;
}

interface WizardStepSummaryProps {
  className?: string;
}

export function WizardStepSummary({ className = '' }: WizardStepSummaryProps): JSX.Element {
  const { t } = useTranslation();
  const slug = useProjectStore((s) => s.wizardData.slug);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<SummaryData | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    apiFetch<SummaryData>(`/api/projects/${encodeURIComponent(slug)}/summary`)
      .then(setData)
      .catch(() => setError(t('wizard.summary_error')))
      .finally(() => setLoading(false));
  }, [slug, t]);

  if (loading) {
    return (
      <div className={`flex items-center justify-center gap-2 py-12 ${className}`}>
        <Spinner size="sm" />
        <span className="text-sm text-content-secondary">{t('wizard.loading_summary')}</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={`text-center py-12 ${className}`}>
        <p className="text-sm text-content-tertiary">{error || t('wizard.no_summary')}</p>
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-4 max-w-3xl ${className}`}>
      <h3 className="text-sm font-semibold text-content-primary">{t('wizard.summary_title')}</h3>

      {/* LLM-generated summary */}
      {data.summary && (
        <div className="rounded-lg border border-border bg-surface-primary p-6 text-sm min-h-[400px] max-h-[70vh] overflow-y-auto">
          <MarkdownRenderer content={data.summary} />
        </div>
      )}

      {/* Facts validated during onboarding (collapsible) */}
      {data.facts.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-semibold text-content-secondary uppercase tracking-wide hover:text-content-primary">
            {t('wizard.validated_facts')} ({data.facts.length})
          </summary>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
            {data.facts.map((fact, i) => (
              <div
                key={i}
                className="rounded-lg border border-border bg-surface-primary p-3"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-semibold text-content-primary">{fact.name}</span>
                  <Badge size="sm" color="blue" variant="tag">{fact.type}</Badge>
                </div>
                <ul className="text-xs text-content-secondary space-y-0.5">
                  {fact.observations.map((obs, j) => (
                    <li key={j}>- {obs}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      )}

      {!data.summary && data.facts.length === 0 && (
        <p className="text-sm text-content-tertiary text-center py-6">
          {t('wizard.no_data_collected')}
        </p>
      )}
    </div>
  );
}
