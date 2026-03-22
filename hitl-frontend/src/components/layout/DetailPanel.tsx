import { type ReactNode, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

interface DetailPanelProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function DetailPanel({
  open,
  onClose,
  title,
  children,
  actions,
  className = '',
}: DetailPanelProps): JSX.Element | null {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-30 bg-black/40 sm:hidden" onClick={onClose} />
      <div
        ref={panelRef}
        className={[
          'fixed z-40 bg-surface-secondary border-l border-border flex flex-col',
          'inset-0 sm:inset-auto sm:right-0 sm:top-0 sm:bottom-0 sm:w-[400px]',
          'animate-[slideInRight_0.2s_ease-out]',
          className,
        ].join(' ')}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-base font-semibold truncate">{title}</h2>
          <button
            onClick={onClose}
            className="text-content-tertiary hover:text-content-primary transition-colors"
            aria-label={t('common.cancel')}
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
        {actions && (
          <div className="flex gap-3 border-t border-border px-4 py-3">{actions}</div>
        )}
      </div>
    </>
  );
}
