import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { LogViewer } from '../components/features/logs/LogViewer';
import * as logsApi from '../api/logs';

const DEFAULT_TAIL = 200;
const TAIL_OPTIONS = [100, 200, 500, 1000, 2000];

export function LogsPage(): JSX.Element {
  const { t } = useTranslation();
  const [containers, setContainers] = useState<string[]>([]);
  const [selected, setSelected] = useState('langgraph-api');
  const [tail, setTail] = useState(DEFAULT_TAIL);

  useEffect(() => {
    logsApi.listContainers().then((list) => {
      setContainers(list);
      if (list.length > 0 && !list.includes(selected)) {
        setSelected(list[0]);
      }
    }).catch(() => {
      setContainers(['langgraph-api', 'langgraph-hitl']);
    });
  }, []);

  return (
    <PageContainer className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex items-center gap-4 mb-4">
        <h2 className="text-xl font-semibold">{t('logs.title')}</h2>
        <div className="flex items-center gap-2 ml-auto">
          <label className="text-xs text-content-tertiary">{t('logs.container')}</label>
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="rounded bg-surface-tertiary border border-border px-2 py-1 text-sm text-content-primary"
          >
            {containers.map((c) => (
              <option key={c} value={c}>{c.replace('langgraph-', '')}</option>
            ))}
          </select>
          <label className="text-xs text-content-tertiary ml-2">{t('logs.lines')}</label>
          <select
            value={tail}
            onChange={(e) => setTail(Number(e.target.value))}
            className="rounded bg-surface-tertiary border border-border px-2 py-1 text-sm text-content-primary"
          >
            {TAIL_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex-1 rounded-lg border border-border overflow-hidden">
        <LogViewer container={selected} tail={tail} />
      </div>
    </PageContainer>
  );
}
