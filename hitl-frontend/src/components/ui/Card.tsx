import type { ReactNode } from 'react';

type CardVariant = 'flat' | 'elevated' | 'interactive';

interface CardProps {
  variant?: CardVariant;
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

const variantStyles: Record<CardVariant, string> = {
  flat: 'bg-surface-secondary border border-border',
  elevated: 'bg-surface-secondary border border-border shadow-lg shadow-black/20',
  interactive: [
    'bg-surface-secondary border border-border',
    'hover:bg-surface-hover hover:border-border-strong',
    'cursor-pointer transition-colors',
  ].join(' '),
};

export function Card({
  variant = 'flat',
  children,
  className = '',
  onClick,
}: CardProps): JSX.Element {
  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick();
        }
      }}
      className={`rounded-xl p-4 ${variantStyles[variant]} ${className}`}
    >
      {children}
    </div>
  );
}
