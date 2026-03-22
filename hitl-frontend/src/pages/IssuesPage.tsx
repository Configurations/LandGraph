import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageContainer } from '../components/layout/PageContainer';
import { DetailPanel } from '../components/layout/DetailPanel';
import { IssueList } from '../components/features/pm/IssueList';
import { IssueDetail } from '../components/features/pm/IssueDetail';
import { IssueCreateModal } from '../components/features/pm/IssueCreateModal';
import { AddRelationModal } from '../components/features/pm/AddRelationModal';
import { GroupBySelector } from '../components/features/pm/GroupBySelector';
import { Button } from '../components/ui/Button';
import { useIssueStore } from '../stores/issueStore';
import { useTeamStore } from '../stores/teamStore';
import * as issuesApi from '../api/issues';
import * as relationsApi from '../api/relations';
import type { IssueCreatePayload, IssueDetail as IssueDetailType, IssueUpdatePayload, RelationCreatePayload } from '../api/types';

export function IssuesPage(): JSX.Element {
  const { t } = useTranslation();
  const { issues, loading, groupBy, selectedId, loadIssues, setSelected, setGroupBy } = useIssueStore();
  const activeTeamId = useTeamStore((s) => s.activeTeamId);

  const [detail, setDetail] = useState<IssueDetailType | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [relationOpen, setRelationOpen] = useState(false);

  useEffect(() => {
    void loadIssues();
  }, [loadIssues]);

  const loadDetail = useCallback(async (id: string) => {
    const data = await issuesApi.getIssue(id);
    setDetail(data);
  }, []);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
    else setDetail(null);
  }, [selectedId, loadDetail]);

  const handleCreate = async (payload: IssueCreatePayload) => {
    if (!activeTeamId) return;
    await issuesApi.createIssue(activeTeamId, payload);
    void loadIssues();
  };

  const handleUpdate = async (data: IssueUpdatePayload) => {
    if (!selectedId) return;
    await issuesApi.updateIssue(selectedId, data);
    void loadDetail(selectedId);
    void loadIssues();
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    await issuesApi.deleteIssue(selectedId);
    setSelected(null);
    void loadIssues();
  };

  const handleRelationCreated = async (payload: RelationCreatePayload) => {
    if (!selectedId) return;
    await relationsApi.createRelation(selectedId, payload);
    void loadDetail(selectedId);
  };

  return (
    <PageContainer>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <h2 className="text-xl font-semibold">{t('issue.issues')}</h2>
        <div className="flex items-center gap-2">
          <GroupBySelector value={groupBy} onChange={setGroupBy} className="w-40" />
          <Button onClick={() => setCreateOpen(true)}>{t('issue.create')}</Button>
        </div>
      </div>

      <IssueList issues={issues} loading={loading} onSelect={setSelected} groupBy={groupBy} />

      <DetailPanel
        open={!!detail}
        onClose={() => setSelected(null)}
        title={detail?.id ?? ''}
      >
        {detail && (
          <IssueDetail
            issue={detail}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
            onAddRelation={() => setRelationOpen(true)}
          />
        )}
      </DetailPanel>

      <IssueCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleCreate}
        teamId={activeTeamId ?? ''}
      />

      {selectedId && (
        <AddRelationModal
          open={relationOpen}
          onClose={() => setRelationOpen(false)}
          onCreated={handleRelationCreated}
          sourceIssueId={selectedId}
        />
      )}
    </PageContainer>
  );
}
