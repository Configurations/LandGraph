import { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { buildStreamUrl } from '../../../api/logs';

interface LogViewerProps {
  container: string;
  tail: number;
}

export function LogViewer({ container, tail }: LogViewerProps): JSX.Element {
  const { t } = useTranslation();
  const [lines, setLines] = useState<string[]>([]);
  const [paused, setPaused] = useState(false);
  const [status, setStatus] = useState<'connected' | 'disconnected' | 'reconnecting'>('disconnected');
  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const pausedRef = useRef(paused);

  // Keep ref in sync for the EventSource callback
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  // Auto-scroll when new lines arrive (only if not paused)
  useEffect(() => {
    if (!paused && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, paused]);

  // Connect / reconnect SSE
  useEffect(() => {
    const url = buildStreamUrl(container, tail);
    setLines([]);
    setStatus('reconnecting');

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setStatus('connected');

    es.onmessage = (ev) => {
      if (!pausedRef.current) {
        setLines((prev) => {
          const next = [...prev, ev.data];
          // Cap at 5000 lines to prevent memory issues
          return next.length > 5000 ? next.slice(-5000) : next;
        });
      }
    };

    es.onerror = () => {
      setStatus('disconnected');
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [container, tail]);

  const handleClear = useCallback(() => setLines([]), []);

  const statusColor = {
    connected: 'bg-green-500',
    disconnected: 'bg-red-500',
    reconnecting: 'bg-yellow-500',
  }[status];

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-surface-secondary border-b border-border">
        <span className={`h-2 w-2 rounded-full ${statusColor}`} />
        <span className="text-xs text-content-tertiary">{t(`logs.${status}`)}</span>
        <div className="flex-1" />
        <button
          onClick={() => setPaused((p) => !p)}
          className="px-3 py-1 text-xs rounded bg-surface-tertiary hover:bg-surface-hover text-content-secondary"
        >
          {paused ? t('logs.resume') : t('logs.pause')}
        </button>
        <button
          onClick={handleClear}
          className="px-3 py-1 text-xs rounded bg-surface-tertiary hover:bg-surface-hover text-content-secondary"
        >
          {t('logs.clear')}
        </button>
      </div>

      {/* Log output */}
      <div className="flex-1 overflow-y-auto bg-black px-4 py-2 font-mono text-xs leading-5 text-green-400">
        {lines.map((line, i) => {
          const lower = line.toLowerCase();
          let color = '';
          if (lower.includes('error') || lower.includes('critical') || lower.includes('fatal') || lower.includes('exception') || lower.includes('traceback')) {
            color = 'text-red-400';
          } else if (lower.includes('warning') || lower.includes('warn')) {
            color = 'text-orange-400';
          }
          return (
            <div key={i} className={`whitespace-pre-wrap break-all ${color}`}>
              {line}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
