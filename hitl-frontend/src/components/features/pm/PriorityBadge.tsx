import type { IssuePriority } from '../../../api/types';

interface PriorityBadgeProps {
  priority: IssuePriority;
  className?: string;
}

const barColors: Record<IssuePriority, string> = {
  1: 'bg-accent-red',
  2: 'bg-accent-orange',
  3: 'bg-accent-yellow',
  4: 'bg-content-quaternary',
};

const barHeights = [3, 5, 7, 9];

export function PriorityBadge({
  priority,
  className = '',
}: PriorityBadgeProps): JSX.Element {
  const activeColor = barColors[priority];
  const activeBars = 5 - priority;

  return (
    <div
      className={`flex items-end gap-[1.5px] h-[10px] ${className}`}
      title={`P${priority}`}
    >
      {barHeights.map((h, i) => (
        <div
          key={i}
          className={`w-[2.5px] rounded-sm ${i < activeBars ? activeColor : 'bg-surface-hover'}`}
          style={{ height: `${h}px` }}
        />
      ))}
    </div>
  );
}
