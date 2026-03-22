import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { DetailPanel } from '../components/layout/DetailPanel';
import { PRList } from '../components/features/pm/PRList';
import { PRDetail } from '../components/features/pm/PRDetail';
import { usePRStore } from '../stores/prStore';
import * as prsApi from '../api/prs';
import type { PRResponse } from '../api/types';

export function ReviewsPage(): JSX.Element {
  const { t } = useTranslation();
  const { prs, loading, statusFilter, selectedId, loadPRs, setSelected, setStatusFilter } =
    usePRStore();
  const [detail, setDetail] = useState<PRResponse | null>(null);

  useEffect(() => {
    void loadPRs();
  }, [loadPRs, statusFilter]);

  const loadDetail = useCallback(async (id: string) => {
    const data = await prsApi.getPR(id);
    setDetail(data);
  }, []);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
    else setDetail(null);
  }, [selectedId, loadDetail]);

  const handleUpdated = () => {
    if (selectedId) void loadDetail(selectedId);
    void loadPRs();
  };

  return (
    <PageContainer>
      <h2 className="text-xl font-semibold mb-6">{t('pr.title')}</h2>

      <PRList
        prs={prs}
        loading={loading}
        statusFilter={statusFilter}
        onFilterChange={setStatusFilter}
        onSelect={setSelected}
      />

      <DetailPanel
        open={!!detail}
        onClose={() => setSelected(null)}
        title={detail?.title ?? ''}
      >
        {detail && <PRDetail pr={detail} onUpdated={handleUpdated} />}
      </DetailPanel>
    </PageContainer>
  );
}
