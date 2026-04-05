import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import { Spinner } from '../../ui/Spinner';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import { useProjectStore } from '../../../stores/projectStore';
import { apiFetch } from '../../../api/client';

interface Deliverable {
  name: string;
  path: string;
  content: string;
}

interface AgentSynthesis {
  agent: string;
  content: string;
}

interface SummaryData {
  project_name: string;
  summary: string;
  facts: Array<{ name: string; type: string; observations: string[] }>;
  rag_summary: string;
  deliverables?: Deliverable[];
  agent_syntheses?: AgentSynthesis[];
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

      {/* Agent syntheses */}
      {data.agent_syntheses && data.agent_syntheses.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-xs font-semibold text-content-secondary uppercase tracking-wide">
            {t('wizard.agent_syntheses')}
          </h4>
          {data.agent_syntheses.map((s) => (
            <details key={s.agent} open className="rounded-lg border border-border bg-surface-primary">
              <summary className="cursor-pointer px-4 py-2 text-sm font-semibold text-content-primary hover:bg-surface-secondary flex items-center gap-2">
                <span className="text-xs">🤖</span> {s.agent}
              </summary>
              <div className="px-4 pb-4 max-h-[60vh] overflow-y-auto text-sm">
                <MarkdownRenderer content={s.content} />
              </div>
            </details>
          ))}
        </div>
      )}

      {/* Raw deliverables — hidden when syntheses exist, otherwise collapsed */}
      {(() => {
        const hasSyntheses = (data.agent_syntheses || []).length > 0;
        const allDels = (data.deliverables || []).filter(d => d.content.length >= 200);
        if (!allDels.length) return null;
        const groups: Record<string, Deliverable[]> = {};
        for (const d of allDels) {
          const parts = d.path.split('/');
          const agent = parts.length >= 3 ? parts[parts.length - 2] : 'other';
          (groups[agent] ??= []).push(d);
        }
        return (
          <details className={hasSyntheses ? '' : 'open'}>
            <summary className="cursor-pointer text-xs font-semibold text-content-tertiary uppercase tracking-wide hover:text-content-secondary py-1">
              {t('wizard.deliverables')} ({allDels.length}) — {hasSyntheses ? 'fichiers bruts' : 'par agent'}
            </summary>
          <div className="flex flex-col gap-2 mt-2">
            {Object.entries(groups).map(([agent, dels]) => (
              <details key={agent} className="group">
                <summary className="cursor-pointer text-sm font-semibold text-content-primary hover:text-accent-blue flex items-center gap-2 py-1">
                  <span className="text-xs">🤖</span> {agent} <span className="text-xs text-content-tertiary font-normal">({dels.length})</span>
                </summary>
                <div className="flex flex-col gap-1 ml-4 mt-1">
                  {dels.map((d, i) => (
                    <details key={i} className="rounded-lg border border-border bg-surface-primary">
                      <summary className="cursor-pointer px-3 py-1.5 text-xs font-medium text-content-primary hover:bg-surface-secondary flex items-center gap-2">
                        <span className="text-content-tertiary">📄</span>
                        {d.name}
                      </summary>
                      <div className="px-3 pb-3 max-h-[50vh] overflow-y-auto text-sm">
                        <MarkdownRenderer content={d.content} />
                      </div>
                    </details>
                  ))}
                </div>
              </details>
            ))}
          </div>
          </details>
        );
      })()}

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
