import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { DetailPanel } from '../components/layout/DetailPanel';
import { DeliverableList } from '../components/features/deliverable/DeliverableList';
import { DeliverableDetail } from '../components/features/deliverable/DeliverableDetail';
import { Select } from '../components/ui/Select';
import { useDeliverableStore } from '../stores/deliverableStore';
import * as deliverablesApi from '../api/deliverables';
import type { DeliverableDetail as DeliverableDetailType } from '../api/types';

export function ProjectDeliverablesPage(): JSX.Element {
  const { t } = useTranslation();
  const { slug = '' } = useParams<{ slug: string }>();
  const deliverables = useDeliverableStore((s) => s.deliverables);
  const loading = useDeliverableStore((s) => s.loading);
  const selectedId = useDeliverableStore((s) => s.selectedId);
  const filters = useDeliverableStore((s) => s.filters);
  const loadDeliverables = useDeliverableStore((s) => s.loadDeliverables);
  const setSelected = useDeliverableStore((s) => s.setSelected);
  const setFilters = useDeliverableStore((s) => s.setFilters);

  const [detail, setDetail] = useState<DeliverableDetailType | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    if (slug) void loadDeliverables(slug);
  }, [slug, filters, loadDeliverables]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    deliverablesApi
      .getDeliverable(selectedId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  const handleValidate = useCallback(
    async (verdict: 'approved' | 'rejected', comment?: string) => {
      if (!selectedId) return;
      await deliverablesApi.validateDeliverable(selectedId, verdict, comment);
      void loadDeliverables(slug);
      setSelected(null);
    },
    [selectedId, slug, loadDeliverables, setSelected],
  );

  const handleRemark = useCallback(
    async (comment: string) => {
      if (!selectedId) return;
      await deliverablesApi.submitRemark(selectedId, comment);
    },
    [selectedId],
  );

  const statusOptions = [
    { value: '', label: t('deliverable.all_statuses') },
    { value: 'pending', label: t('deliverable.status_pending') },
    { value: 'approved', label: t('deliverable.status_approved') },
    { value: 'rejected', label: t('deliverable.status_rejected') },
  ];

  return (
    <PageContainer>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <h2 className="text-xl font-semibold">{t('deliverable.deliverables')}</h2>
        <div className="flex gap-2">
          <Select
            options={statusOptions}
            value={filters.status}
            onChange={(e) => setFilters({ status: e.target.value })}
            className="w-36"
          />
        </div>
      </div>

      <DeliverableList
        deliverables={deliverables}
        loading={loading}
        onSelect={setSelected}
      />

      <DetailPanel
        open={!!selectedId}
        onClose={() => setSelected(null)}
        title={detail?.key ?? t('common.loading')}
      >
        {detail && !detailLoading && (
          <DeliverableDetail
            deliverable={detail}
            onValidate={handleValidate}
            onRemark={handleRemark}
          />
        )}
      </DetailPanel>
    </PageContainer>
  );
}
