import { useEffect, useMemo, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import { Badge } from '../../ui/Badge';
import { Spinner } from '../../ui/Spinner';
import { ProjectTypeCard } from './ProjectTypeCard';
import type { PhaseInfo } from './WorkflowBlock';
import * as projectTypesApi from '../../../api/projectTypes';
import type { ProjectTypeResponse } from '../../../api/types';

interface ProjectTypeSelectorProps {
  selectedTypeId: string | null;
  selectedChatId: string | null;
  selectedWorkflowIds: string[];
  onSelect: (typeId: string | null, chatId: string | null, workflowIds: string[], workflowFilename?: string) => void;
  className?: string;
}

export function ProjectTypeSelector({
  selectedTypeId,
  selectedChatId,
  selectedWorkflowIds,
  onSelect,
  className = '',
}: ProjectTypeSelectorProps): JSX.Element {
  const { t } = useTranslation();
  const [types, setTypes] = useState<ProjectTypeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedWfIdx, setExpandedWfIdx] = useState<number | null>(null);
  const [phasesMap, setPhasesMap] = useState<Record<string, PhaseInfo[]>>({});

  useEffect(() => {
    setLoading(true);
    projectTypesApi
      .listProjectTypes()
      .then(setTypes)
      .catch(() => setTypes([]))
      .finally(() => setLoading(false));
  }, []);

  const selectedType = useMemo(
    () => types.find((pt) => pt.id === selectedTypeId) ?? null,
    [types, selectedTypeId],
  );

  // Load phases for all workflows of the selected type
  useEffect(() => {
    if (!selectedType) {
      setPhasesMap({});
      return;
    }
    let cancelled = false;
    async function loadPhases() {
      const map: Record<string, PhaseInfo[]> = {};
      for (const wf of selectedType!.workflows) {
        try {
          const resolved = await projectTypesApi.fetchResolvedPhases(selectedType!.id, wf.filename);
          map[wf.filename] = resolved.map((p: any) => ({
            id: p.id,
            name: p.name || p.id.replace(/_/g, ' '),
            order: p.order ?? 0,
            agents: (p.agents || []).map((a: string) => ({ id: a, role: '', required: false })),
            deliverables: (p.deliverables || []).map((d: any) => ({ key: d.key, name: d.name, required: false, type: d.type || '' })),
            humanGate: p.humanGate ?? false,
          }));
        } catch {
          map[wf.filename] = [];
        }
      }
      if (!cancelled) setPhasesMap(map);
    }
    loadPhases();
    return () => { cancelled = true; };
  }, [selectedType]);

  const handleTypeSelect = useCallback((typeId: string) => {
    const pt = types.find((t) => t.id === typeId);
    const wf = pt?.workflows[0];
    // Auto-select all workflows
    const wfIds = pt?.workflows.map((w) => w.filename) ?? [];
    onSelect(typeId, null, wfIds, wf?.filename);
    setExpandedWfIdx(null);
  }, [types, onSelect]);

  const handleChatSelect = useCallback((chatId: string) => {
    const newChatId = chatId === selectedChatId ? null : chatId;
    onSelect(selectedTypeId, newChatId, selectedWorkflowIds);
  }, [selectedTypeId, selectedChatId, selectedWorkflowIds, onSelect]);

  const handleWorkflowToggle = useCallback((filename: string) => {
    const newIds = selectedWorkflowIds.includes(filename)
      ? selectedWorkflowIds.filter((id) => id !== filename)
      : [...selectedWorkflowIds, filename];
    onSelect(selectedTypeId, selectedChatId, newIds);
  }, [selectedTypeId, selectedChatId, selectedWorkflowIds, onSelect]);

  if (loading) {
    return (
      <div className={`flex justify-center py-8 ${className}`}>
        <Spinner />
      </div>
    );
  }

  if (types.length === 0) {
    return (
      <div className={`text-center py-8 ${className}`}>
        <p className="text-sm text-content-tertiary">{t('project_type.no_types')}</p>
        <Button variant="ghost" size="sm" onClick={() => onSelect(null, null, [])} className="mt-3">
          {t('project_type.skip')}
        </Button>
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-6 ${className}`}>
      {/* Section 1: Project Type */}
      <div>
        <h3 className="text-sm font-semibold text-content-secondary mb-3">
          {t('project_type.select_type')}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {types.map((pt) => (
            <ProjectTypeCard
              key={pt.id}
              projectType={pt}
              selected={selectedTypeId === pt.id}
              onSelect={handleTypeSelect}
            />
          ))}
        </div>
      </div>

      {/* Section 2: Chat Onboarding (visible after type selection) */}
      {selectedType && selectedType.chats.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-content-secondary mb-3">
            {t('project_type.select_chat')}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {selectedType.chats.map((chat) => (
              <button
                key={chat.id}
                onClick={() => handleChatSelect(chat.id)}
                className={[
                  'flex flex-col gap-2 rounded-xl border-2 p-4 text-left transition-all',
                  'hover:border-accent-blue/60 hover:bg-surface-hover',
                  selectedChatId === chat.id
                    ? 'border-accent-blue bg-accent-blue/5'
                    : 'border-border bg-surface-secondary',
                ].join(' ')}
              >
                <h4 className="text-sm font-semibold text-content-primary">
                  {chat.id.replace(/_/g, ' ')}
                </h4>
                <p className="text-xs text-content-tertiary">
                  {chat.type}
                </p>
                <div className="flex flex-wrap gap-1 mt-auto pt-2">
                  {chat.agents.map((a) => (
                    <Badge key={a} color="blue" size="sm">{a}</Badge>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Section 3: Workflows (visible after type selection) */}
      {selectedType && selectedType.workflows.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-content-secondary mb-3">
            {t('project_type.select_workflows')}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {selectedType.workflows.map((wf, i) => (
              <button
                key={wf.filename}
                onClick={() => handleWorkflowToggle(wf.filename)}
                className={[
                  'flex flex-col gap-2 rounded-xl border-2 p-4 text-left transition-all',
                  'hover:border-accent-blue/60 hover:bg-surface-hover',
                  selectedWorkflowIds.includes(wf.filename)
                    ? 'border-accent-blue bg-accent-blue/5'
                    : 'border-border bg-surface-secondary',
                ].join(' ')}
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-content-primary truncate">
                    {wf.name}
                  </h4>
                  <span
                    className="text-xs text-accent-blue cursor-pointer"
                    onClick={(e) => {
                      e.stopPropagation();
                      setExpandedWfIdx(expandedWfIdx === i ? null : i);
                    }}
                  >
                    {expandedWfIdx === i ? '▼' : '▶'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge color={wf.mode === 'sequential' ? 'green' : 'red'} size="sm">
                    {wf.mode}
                  </Badge>
                  <Badge color="purple" size="sm">
                    prio: {wf.priority}
                  </Badge>
                </div>
              </button>
            ))}
          </div>

          {/* Inline phase cards for expanded workflow */}
          {expandedWfIdx !== null && selectedType.workflows[expandedWfIdx] && (() => {
            const phases = (phasesMap[selectedType.workflows[expandedWfIdx].filename] ?? [])
              .sort((a, b) => a.order - b.order);
            return phases.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {phases.map((phase, i) => (
                  <div key={phase.id} className="flex items-center gap-1">
                    <div className="w-[160px] bg-surface-secondary rounded-lg p-2.5 border-l-2 border-accent-blue">
                      <div className="text-[10px] font-bold text-accent-blue mb-1">{phase.name}</div>
                      {phase.agents.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {phase.agents.map((a) => (
                            <span key={a.id} className="text-[9px] text-content-tertiary bg-surface-tertiary rounded px-1">{a.id}</span>
                          ))}
                        </div>
                      )}
                      {phase.humanGate && (
                        <div className="text-[9px] text-accent-orange mt-1">🔒 gate</div>
                      )}
                    </div>
                    {i < phases.length - 1 && (
                      <span className="text-accent-blue text-xs">→</span>
                    )}
                  </div>
                ))}
              </div>
            ) : null;
          })()}
        </div>
      )}

      <Button variant="ghost" size="sm" onClick={() => onSelect(null, null, [])} className="self-start">
        {t('project_type.skip')}
      </Button>
    </div>
  );
}
