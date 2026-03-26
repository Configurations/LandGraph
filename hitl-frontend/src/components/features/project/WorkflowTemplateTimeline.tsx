import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Spinner } from '../../ui/Spinner';
import { WorkflowBlock } from './WorkflowBlock';
import type { PhaseInfo } from './WorkflowBlock';
import * as projectTypesApi from '../../../api/projectTypes';
import type { ProjectTypeResponse } from '../../../api/types';

interface WorkflowTemplateTimelineProps {
  projectType: ProjectTypeResponse;
}

/**
 * Timeline verticale des workflows d'un type de projet (templates).
 * Affiche dots + ligne à gauche, blocs workflow dépliables à droite.
 */
export function WorkflowTemplateTimeline({
  projectType,
}: WorkflowTemplateTimelineProps): JSX.Element {
  const { t } = useTranslation();
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [phasesMap, setPhasesMap] = useState<Record<string, PhaseInfo[]>>({});
  const [loading, setLoading] = useState(true);

  // Sort workflows by priority (descending = highest first)
  const workflows = [...projectType.workflows].sort(
    (a, b) => (b.priority ?? 50) - (a.priority ?? 50),
  );

  // Load phase files for each workflow to build a minimal phases list
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    async function loadPhases() {
      const map: Record<string, PhaseInfo[]> = {};
      for (const wf of projectType.workflows) {
        try {
          const files = await projectTypesApi.fetchPhaseFiles(
            projectType.id,
            wf.filename,
          );
          map[wf.filename] = files.map((f, idx) => ({
            id: f.phase_id,
            name: f.phase_id.replace(/_/g, ' '),
            order: idx + 1,
            agents: [],
            deliverables: [],
            humanGate: false,
          }));
        } catch {
          map[wf.filename] = [];
        }
      }
      if (!cancelled) {
        setPhasesMap(map);
        setLoading(false);
      }
    }
    loadPhases();
    return () => {
      cancelled = true;
    };
  }, [projectType.id, projectType.workflows]);

  const handleToggle = useCallback((idx: number) => {
    setExpandedIdx((prev) => (prev === idx ? null : idx));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-6">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="flex gap-4 mt-4">
      {/* Timeline dots + line */}
      <div
        className="flex flex-col items-center pt-4 flex-shrink-0"
        style={{ width: 20 }}
      >
        {workflows.map((wf, i) => (
          <div key={wf.filename} className="flex flex-col items-center">
            <div
              className={[
                'w-3 h-3 rounded-full flex-shrink-0',
                expandedIdx === i || i === 0 ? 'bg-accent-blue' : 'bg-border',
              ].join(' ')}
            />
            {i < workflows.length - 1 && (
              <div
                className={[
                  'w-0.5 min-h-[48px] flex-1',
                  i < (expandedIdx ?? 0) ? 'bg-accent-blue' : 'bg-border',
                ].join(' ')}
              />
            )}
          </div>
        ))}
      </div>

      {/* Workflow blocks */}
      <div className="flex-1 flex flex-col gap-2">
        {workflows.map((wf, i) => (
          <div key={wf.filename}>
            <WorkflowBlock
              typeId={projectType.id}
              workflow={wf}
              expanded={expandedIdx === i}
              onToggle={() => handleToggle(i)}
              phases={phasesMap[wf.filename] ?? []}
            />
            {/* Dependency arrow */}
            {i < workflows.length - 1 && workflows[i + 1].depends_on && (
              <div className="flex items-center gap-2 py-1 pl-2">
                <span className="text-accent-orange text-[10px]">
                  ⬇ {t('multi_workflow.depends_on')}:{' '}
                  {workflows[i + 1].depends_on}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
