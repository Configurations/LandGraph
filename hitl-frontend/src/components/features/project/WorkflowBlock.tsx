import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import { Spinner } from '../../ui/Spinner';
import * as projectTypesApi from '../../../api/projectTypes';
import type { WorkflowTemplate, PhaseFile, PhaseFileContent } from '../../../api/types';

type Tab = 'phases' | 'prompt' | 'files';

interface WorkflowBlockProps {
  typeId: string;
  workflow: WorkflowTemplate;
  expanded: boolean;
  onToggle: () => void;
  /** Phases parsed from the .wrk.json (passed by parent) */
  phases: PhaseInfo[];
}

export interface PhaseInfo {
  id: string;
  name: string;
  order: number;
  agents: { id: string; role: string; required: boolean }[];
  deliverables: { key: string; name: string; required: boolean; type: string }[];
  humanGate: boolean;
}

export function WorkflowBlock({
  typeId,
  workflow,
  expanded,
  onToggle,
  phases,
}: WorkflowBlockProps): JSX.Element {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<Tab>('phases');

  // Phase files
  const [phaseFiles, setPhaseFiles] = useState<PhaseFile[]>([]);
  const [filesLoaded, setFilesLoaded] = useState(false);
  const [openFileId, setOpenFileId] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<PhaseFileContent | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);

  // Orchestrator prompt = first phase file content
  const [orchestratorPrompt, setOrchestratorPrompt] = useState<string | null>(null);
  const [loadingPrompt, setLoadingPrompt] = useState(false);

  // Load phase files when expanded + files tab
  useEffect(() => {
    if (!expanded || filesLoaded) return;
    projectTypesApi
      .fetchPhaseFiles(typeId, workflow.filename)
      .then((files) => {
        setPhaseFiles(files);
        setFilesLoaded(true);
      });
  }, [expanded, filesLoaded, typeId, workflow.filename]);

  // Load orchestrator prompt when prompt tab
  useEffect(() => {
    if (!expanded || activeTab !== 'prompt' || orchestratorPrompt !== null) return;
    if (phaseFiles.length === 0 && !filesLoaded) return;
    const firstFile = phaseFiles[0];
    if (!firstFile) {
      setOrchestratorPrompt('');
      return;
    }
    setLoadingPrompt(true);
    projectTypesApi
      .fetchPhaseFileContent(typeId, workflow.filename, firstFile.phase_id)
      .then((fc) => setOrchestratorPrompt(fc?.content ?? ''))
      .finally(() => setLoadingPrompt(false));
  }, [expanded, activeTab, orchestratorPrompt, phaseFiles, filesLoaded, typeId, workflow.filename]);

  const handleFileClick = useCallback(
    (phaseId: string) => {
      if (openFileId === phaseId) {
        setOpenFileId(null);
        setFileContent(null);
        return;
      }
      setOpenFileId(phaseId);
      setLoadingContent(true);
      projectTypesApi
        .fetchPhaseFileContent(typeId, workflow.filename, phaseId)
        .then((fc) => setFileContent(fc))
        .finally(() => setLoadingContent(false));
    },
    [openFileId, typeId, workflow.filename],
  );

  const totalAgents = new Set(phases.flatMap((p) => p.agents.map((a) => a.id))).size;
  const totalDeliverables = phases.reduce((n, p) => n + p.deliverables.length, 0);

  return (
    <div
      className={[
        'rounded-lg border overflow-hidden transition-colors',
        expanded ? 'border-accent-blue' : 'border-border',
      ].join(' ')}
    >
      {/* Header */}
      <button
        onClick={onToggle}
        className={[
          'w-full flex items-center justify-between px-4 py-3 text-left transition-colors',
          expanded ? 'bg-surface-hover' : 'bg-surface-secondary hover:bg-surface-hover',
        ].join(' ')}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-sm font-semibold text-content-primary truncate">
            {workflow.name}
          </span>
          <Badge
            color={workflow.mode === 'sequential' ? 'green' : 'red'}
            size="sm"
          >
            {t(`multi_workflow.mode_${workflow.mode}`)}
          </Badge>
          <Badge color="purple" size="sm">
            prio: {workflow.priority}
          </Badge>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {!expanded && (
            <span className="text-xs text-content-tertiary">
              {phases.length} phases · {totalAgents} agents · {totalDeliverables} livrables
            </span>
          )}
          <span className="text-content-tertiary text-xs">
            {expanded ? '▼' : '▶'}
          </span>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <>
          {/* Tabs */}
          <div className="flex border-b border-border bg-surface-primary">
            {(['phases', 'prompt', 'files'] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={[
                  'px-4 py-2 text-xs font-medium border-b-2 transition-colors',
                  activeTab === tab
                    ? 'border-accent-blue text-accent-blue'
                    : 'border-transparent text-content-tertiary hover:text-content-secondary',
                ].join(' ')}
              >
                {t(`project_type.tab_${tab}`)}
              </button>
            ))}
          </div>

          {/* Tab: Phases */}
          {activeTab === 'phases' && (
            <div className="p-4 flex gap-3 overflow-x-auto">
              {phases
                .sort((a, b) => a.order - b.order)
                .map((phase, i) => (
                  <div key={phase.id} className="flex items-start gap-2 flex-shrink-0">
                    <div className="min-w-[180px] bg-surface-secondary rounded-lg p-3 border-l-3 border-accent-blue">
                      <div className="text-[10px] font-bold text-accent-blue mb-1">
                        ① {phase.name}
                      </div>
                      {phase.agents.length > 0 && (
                        <div className="mt-2">
                          <div className="text-[10px] text-content-tertiary">
                            {t('workflow.agents')}
                          </div>
                          {phase.agents.map((a) => (
                            <div key={a.id} className="text-xs text-content-secondary">
                              {a.id}
                            </div>
                          ))}
                        </div>
                      )}
                      {phase.deliverables.length > 0 && (
                        <div className="mt-2">
                          <div className="text-[10px] text-content-tertiary">
                            {t('workflow.deliverables')}
                          </div>
                          {phase.deliverables.map((d) => (
                            <div key={d.key} className="text-xs text-content-secondary">
                              {d.name || d.key}
                              {d.required && (
                                <span className="text-accent-green text-[9px] ml-1">required</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {phase.humanGate && (
                        <div className="mt-2 text-[10px] text-accent-orange">
                          🔒 human gate
                        </div>
                      )}
                    </div>
                    {i < phases.length - 1 && (
                      <span className="text-accent-blue self-center text-sm">→</span>
                    )}
                  </div>
                ))}
              {phases.length === 0 && (
                <p className="text-xs text-content-tertiary">
                  {t('workflow.no_content')}
                </p>
              )}
            </div>
          )}

          {/* Tab: Prompt Orchestrateur */}
          {activeTab === 'prompt' && (
            <div className="p-4">
              {loadingPrompt ? (
                <div className="flex justify-center py-4">
                  <Spinner />
                </div>
              ) : orchestratorPrompt ? (
                <>
                  {phaseFiles[0] && (
                    <div className="text-[11px] text-content-tertiary mb-2">
                      📄 {phaseFiles[0].filename}
                    </div>
                  )}
                  <pre className="bg-surface-primary border border-border rounded-lg p-4 text-xs text-content-secondary font-mono whitespace-pre-wrap max-h-[280px] overflow-y-auto leading-relaxed">
                    {orchestratorPrompt}
                  </pre>
                </>
              ) : (
                <p className="text-xs text-content-tertiary">
                  {t('project_type.no_prompt')}
                </p>
              )}
            </div>
          )}

          {/* Tab: Fichiers */}
          {activeTab === 'files' && (
            <div className="p-4">
              {phaseFiles.length === 0 ? (
                <p className="text-xs text-content-tertiary">
                  {t('project_type.no_files')}
                </p>
              ) : (
                <div className="border border-border rounded-lg overflow-hidden">
                  {phaseFiles.map((pf) => (
                    <div key={pf.phase_id}>
                      <button
                        onClick={() => handleFileClick(pf.phase_id)}
                        className={[
                          'w-full flex items-center justify-between px-3 py-2 text-left text-xs border-b border-border last:border-b-0 transition-colors',
                          openFileId === pf.phase_id
                            ? 'bg-surface-hover border-l-2 border-l-accent-blue'
                            : 'hover:bg-surface-hover',
                        ].join(' ')}
                      >
                        <span className="flex items-center gap-2">
                          <span className={openFileId === pf.phase_id ? 'text-accent-blue' : 'text-content-tertiary'}>
                            📝
                          </span>
                          <span className={openFileId === pf.phase_id ? 'text-content-primary' : 'text-content-secondary'}>
                            {pf.filename}
                          </span>
                        </span>
                        <span className="text-content-tertiary text-[10px]">
                          {openFileId === pf.phase_id ? '▼' : '▶'}
                        </span>
                      </button>
                      {openFileId === pf.phase_id && (
                        <div className="px-3 py-3 bg-surface-primary border-b border-border">
                          {loadingContent ? (
                            <div className="flex justify-center py-2">
                              <Spinner />
                            </div>
                          ) : fileContent ? (
                            <pre className="bg-surface-secondary border border-border rounded-lg p-3 text-[11px] text-content-secondary font-mono whitespace-pre-wrap max-h-[220px] overflow-y-auto leading-relaxed">
                              {fileContent.content}
                            </pre>
                          ) : (
                            <p className="text-xs text-content-tertiary">
                              {t('project_type.no_prompt')}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
