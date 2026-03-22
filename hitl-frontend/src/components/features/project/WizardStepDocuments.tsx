import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DocumentDropzone } from './DocumentDropzone';
import { DocumentList } from './DocumentList';
import { Spinner } from '../../ui/Spinner';
import { useProjectStore } from '../../../stores/projectStore';
import * as ragApi from '../../../api/rag';
import type { UploadedFile } from '../../../api/types';

interface WizardStepDocumentsProps {
  className?: string;
}

export function WizardStepDocuments({ className = '' }: WizardStepDocumentsProps): JSX.Element {
  const { t } = useTranslation();
  const slug = useProjectStore((s) => s.wizardData.slug);

  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [vectorizing, setVectorizing] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(true);

  const loadFiles = useCallback(async () => {
    if (!slug) return;
    setLoadingFiles(true);
    try {
      const result = await ragApi.listUploads(slug);
      setFiles(result);
    } catch {
      // handled by apiFetch
    } finally {
      setLoadingFiles(false);
    }
  }, [slug]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  const handleUpload = useCallback(async (file: File) => {
    if (!slug) return;
    setUploading(true);
    try {
      const result = await ragApi.uploadDocument(slug, file);
      setFiles((prev) => [...prev, { name: result.filename, size: result.size, content_type: result.content_type }]);
      if (result.chunks > 0) {
        setVectorizing(true);
        setTimeout(() => setVectorizing(false), 2000);
      }
    } catch {
      // handled by apiFetch
    } finally {
      setUploading(false);
    }
  }, [slug]);

  const handleDelete = useCallback(async (filename: string) => {
    if (!slug) return;
    try {
      await ragApi.deleteUpload(slug, filename);
      setFiles((prev) => prev.filter((f) => f.name !== filename));
    } catch {
      // handled by apiFetch
    }
  }, [slug]);

  return (
    <div className={`flex flex-col gap-4 max-w-lg ${className}`}>
      <DocumentDropzone onUpload={(f) => void handleUpload(f)} uploading={uploading} />

      {vectorizing && (
        <div className="flex items-center gap-2 text-content-secondary">
          <Spinner size="sm" />
          <span className="text-xs">{t('documents.vectorizing')}</span>
        </div>
      )}

      {loadingFiles ? (
        <div className="flex justify-center py-4"><Spinner size="md" /></div>
      ) : (
        <DocumentList files={files} onDelete={(f) => void handleDelete(f)} />
      )}
    </div>
  );
}
