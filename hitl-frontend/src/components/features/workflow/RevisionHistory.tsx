import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import * as deliverablesApi from '../../../api/deliverables';
import type { RemarkResponse } from '../../../api/types';

interface Props {
  artifactId: number;
  version: number;
}

export function RevisionHistory({ artifactId, version }: Props): JSX.Element {
  const { t } = useTranslation();
  const [remarks, setRemarks] = useState<RemarkResponse[]>([]);

  useEffect(() => {
    deliverablesApi.listRemarks(String(artifactId)).then(setRemarks).catch(() => {});
  }, [artifactId, version]);

  if (!remarks.length && version <= 1) return <></>;

  return (
    <div className="border-t border-border mt-4 pt-3">
      <h4 className="text-xs font-semibold text-content-secondary uppercase tracking-wide mb-2">
        {t('workflow.revisions')} ({version})
      </h4>
      <div className="flex flex-col gap-2">
        {remarks.map((r) => (
          <div key={r.id} className="text-xs border-l-2 border-accent-blue pl-3 py-1">
            <div className="text-content-tertiary">
              {r.reviewer} — {new Date(r.created_at).toLocaleString()}
            </div>
            <div className="text-content-secondary mt-0.5">{r.comment}</div>
          </div>
        ))}
        <div className="text-xs text-content-tertiary italic">
          v1 — version initiale
        </div>
      </div>
    </div>
  );
}
