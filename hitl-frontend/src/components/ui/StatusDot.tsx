type Status = 'online' | 'offline' | 'pending' | 'busy';
type DotSize = 'sm' | 'md';

interface StatusDotProps {
  status: Status;
  size?: DotSize;
  className?: string;
}

const statusColors: Record<Status, string> = {
  online: 'bg-accent-green',
  offline: 'bg-content-quaternary',
  pending: 'bg-accent-orange animate-pulse',
  busy: 'bg-accent-red',
};

const sizeStyles: Record<DotSize, string> = {
  sm: 'h-2 w-2',
  md: 'h-3 w-3',
};

export function StatusDot({
  status,
  size = 'sm',
  className = '',
}: StatusDotProps): JSX.Element {
  return (
    <span
      className={[
        'inline-block rounded-full',
        statusColors[status],
        sizeStyles[size],
        className,
      ].join(' ')}
      aria-label={status}
    />
  );
}
