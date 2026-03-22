import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

interface BlockedIssueRef {
  id: string;
  title: string;
}

interface BlockedBannerProps {
  blockedBy: BlockedIssueRef[];
  className?: string;
}

export function BlockedBanner({
  blockedBy,
  className = '',
}: BlockedBannerProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div
      className={`rounded-lg border border-accent-red/30 bg-accent-red/10 px-3 py-2 text-sm ${className}`}
    >
      <span className="font-medium text-accent-red">
        {t('issue.blocked_by')}
      </span>
      <ul className="mt-1 space-y-0.5">
        {blockedBy.map((issue) => (
          <li key={issue.id} className="flex items-center gap-2">
            <Link
              to={`/issues?selected=${issue.id}`}
              className="font-mono text-xs text-accent-red hover:underline"
            >
              {issue.id}
            </Link>
            <span className="text-content-secondary truncate">{issue.title}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
