import { useTranslation } from 'react-i18next';
import { useNotificationStore, type Toast as ToastType } from '../../stores/notificationStore';

type ToastVariant = ToastType['type'];

const variantStyles: Record<ToastVariant, string> = {
  success: 'border-accent-green/40 bg-accent-green/10',
  error: 'border-accent-red/40 bg-accent-red/10',
  info: 'border-accent-blue/40 bg-accent-blue/10',
  warning: 'border-accent-orange/40 bg-accent-orange/10',
};

const iconPaths: Record<ToastVariant, string> = {
  success: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  error: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
  info: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  warning: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z',
};

interface ToastItemProps {
  toast: ToastType;
  className?: string;
}

function ToastItem({ toast, className = '' }: ToastItemProps): JSX.Element {
  const { t } = useTranslation();
  const removeToast = useNotificationStore((s) => s.removeToast);

  return (
    <div
      className={[
        'flex items-start gap-3 rounded-lg border p-3 shadow-lg shadow-black/20',
        'animate-[slideIn_0.2s_ease-out]',
        variantStyles[toast.type],
        className,
      ].join(' ')}
      role="alert"
    >
      <svg className="h-5 w-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={iconPaths[toast.type]} />
      </svg>
      <p className="flex-1 text-sm">{t(toast.messageKey, toast.params)}</p>
      <button
        onClick={() => removeToast(toast.id)}
        className="shrink-0 text-content-tertiary hover:text-content-primary"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

interface ToastContainerProps {
  className?: string;
}

export function ToastContainer({ className = '' }: ToastContainerProps): JSX.Element {
  const toasts = useNotificationStore((s) => s.toasts);

  return (
    <div
      className={[
        'fixed top-4 right-4 z-[100] flex flex-col gap-2 w-80',
        className,
      ].join(' ')}
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
