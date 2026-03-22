import type { IssueStatus } from '../../../api/types';

interface IssueStatusIconProps {
  status: IssueStatus;
  size?: number;
  className?: string;
}

const statusColors: Record<IssueStatus, string> = {
  backlog: 'text-content-quaternary',
  todo: 'text-content-tertiary',
  'in-progress': 'text-accent-blue',
  'in-review': 'text-accent-orange',
  done: 'text-accent-green',
};

export function IssueStatusIcon({
  status,
  size = 16,
  className = '',
}: IssueStatusIconProps): JSX.Element {
  const color = statusColors[status];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      className={`${color} ${className}`}
    >
      {status === 'backlog' && (
        <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2" />
      )}
      {status === 'todo' && (
        <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
      )}
      {status === 'in-progress' && (
        <>
          <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
          <path d="M8 2a6 6 0 010 12V2z" fill="currentColor" />
        </>
      )}
      {status === 'in-review' && (
        <>
          <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
          <path d="M8 4v4l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </>
      )}
      {status === 'done' && (
        <>
          <circle cx="8" cy="8" r="6" fill="currentColor" />
          <path d="M5 8l2 2 4-4" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </>
      )}
    </svg>
  );
}
