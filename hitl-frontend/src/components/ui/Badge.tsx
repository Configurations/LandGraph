import type { ReactNode } from 'react';

type BadgeVariant = 'status' | 'count' | 'tag';
type BadgeColor = 'blue' | 'green' | 'orange' | 'red' | 'purple' | 'yellow';
type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  variant?: BadgeVariant;
  color?: BadgeColor;
  size?: BadgeSize;
  children: ReactNode;
  className?: string;
}

const colorStyles: Record<BadgeColor, string> = {
  blue: 'bg-accent-blue/15 text-accent-blue',
  green: 'bg-accent-green/15 text-accent-green',
  orange: 'bg-accent-orange/15 text-accent-orange',
  red: 'bg-accent-red/15 text-accent-red',
  purple: 'bg-accent-purple/15 text-accent-purple',
  yellow: 'bg-accent-yellow/15 text-accent-yellow',
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'px-1.5 py-0.5 text-[10px]',
  md: 'px-2 py-0.5 text-xs',
};

export function Badge({
  variant = 'tag',
  color = 'blue',
  size = 'md',
  children,
  className = '',
}: BadgeProps): JSX.Element {
  const baseStyle = 'inline-flex items-center font-medium rounded-full';

  const variantExtra =
    variant === 'count'
      ? 'min-w-[20px] justify-center'
      : variant === 'status'
        ? 'gap-1'
        : '';

  return (
    <span
      className={[baseStyle, colorStyles[color], sizeStyles[size], variantExtra, className].join(
        ' ',
      )}
    >
      {variant === 'status' && (
        <span className={`inline-block h-1.5 w-1.5 rounded-full bg-current`} />
      )}
      {children}
    </span>
  );
}
