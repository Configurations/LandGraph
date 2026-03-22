import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '../../ui/Badge';
import { PRActions } from './PRActions';
import * as prsApi from '../../../api/prs';
import type { PRResponse } from '../../../api/types';

interface PRDetailProps {
  pr: PRResponse;
  onUpdated: () => void;
  className?: string;
}

const statusColor: Record<string, 'green' | 'blue' | 'orange' | 'red' | 'purple'> = {
  draft: 'purple',
  open: 'blue',
  approved: 'green',
  changes_requested: 'orange',
  merged: 'green',
  closed: 'red',
};

export function PRDetail({ pr, onUpdated, className = '' }: PRDetailProps): JSX.Element {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);

  const handleApprove = async () => {
    setLoading(true);
    try {
      await prsApi.updatePRStatus(pr.id, { status: 'approved' });
      onUpdated();
    } finally {
      setLoading(false);
    }
  };

  const handleRequestChanges = async () => {
    setLoading(true);
    try {
      await prsApi.updatePRStatus(pr.id, { status: 'changes_requested' });
      onUpdated();
    } finally {
      setLoading(false);
    }
  };

  const handleMerge = async () => {
    setLoading(true);
    try {
      await prsApi.mergePR(pr.id);
      onUpdated();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      <div className="flex items-center gap-2">
        <Badge size="md" color={statusColor[pr.status] ?? 'blue'}>
          {t(`pr.status_${pr.status}`)}
        </Badge>
        <span className="text-xs font-mono text-content-tertiary">
          {pr.branch} &rarr; {pr.target_branch}
        </span>
      </div>

      {pr.description && (
        <p className="text-sm text-content-secondary whitespace-pre-wrap">{pr.description}</p>
      )}

      <div className="grid grid-cols-3 gap-3 rounded-lg border border-border bg-surface-tertiary p-3">
        <div className="text-center">
          <p className="text-lg font-bold text-content-primary">{pr.files_changed}</p>
          <p className="text-xs text-content-tertiary">{t('pr.files')}</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-bold text-accent-green">+{pr.additions}</p>
          <p className="text-xs text-content-tertiary">{t('pr.additions')}</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-bold text-accent-red">-{pr.deletions}</p>
          <p className="text-xs text-content-tertiary">{t('pr.deletions')}</p>
        </div>
      </div>

      <PRActions
        status={pr.status}
        onApprove={handleApprove}
        onRequestChanges={handleRequestChanges}
        onMerge={handleMerge}
        loading={loading}
      />

      {pr.remote_url && (
        <a
          href={pr.remote_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-accent-blue hover:underline"
        >
          {t('pr.view_remote')}
        </a>
      )}
    </div>
  );
}
