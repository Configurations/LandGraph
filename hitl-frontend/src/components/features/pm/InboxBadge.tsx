interface InboxBadgeProps {
  count: number;
  className?: string;
}

export function InboxBadge({ count, className = '' }: InboxBadgeProps): JSX.Element | null {
  if (count <= 0) return null;

  const display = count > 99 ? '99+' : String(count);

  return (
    <span
      className={[
        'inline-flex items-center justify-center min-w-[18px] h-[18px] px-1',
        'rounded-full bg-accent-red text-white text-[10px] font-semibold',
        className,
      ].join(' ')}
    >
      {display}
    </span>
  );
}
