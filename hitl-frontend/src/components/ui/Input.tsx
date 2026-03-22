import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: ReactNode;
  className?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, className = '', id, ...rest }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className={`flex flex-col gap-1.5 ${className}`}>
        {label && (
          <label htmlFor={inputId} className="text-sm font-medium text-content-secondary">
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary">
              {icon}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            className={[
              'w-full rounded-lg border bg-surface-tertiary px-3 py-2 text-sm text-content-primary',
              'placeholder:text-content-quaternary',
              'focus:border-accent-blue focus:outline-none focus:ring-1 focus:ring-accent-blue',
              'transition-colors',
              icon ? 'pl-10' : '',
              error ? 'border-accent-red' : 'border-border',
            ].join(' ')}
            {...rest}
          />
        </div>
        {error && <p className="text-xs text-accent-red">{error}</p>}
      </div>
    );
  },
);

Input.displayName = 'Input';
