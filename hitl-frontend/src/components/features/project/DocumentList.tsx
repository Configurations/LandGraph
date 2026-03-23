import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import type { UploadedFile } from '../../../api/types';

interface DocumentListProps {
  files: UploadedFile[];
  onDelete?: (filename: string) => void;
  className?: string;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(file: UploadedFile): string {
  if (file.type === 'directory') return '\uD83D\uDCC1';
  if (file.content_type.startsWith('image/')) return '\uD83D\uDDBC';
  if (file.content_type === 'application/pdf') return '\uD83D\uDCC4';
  return '\uD83D\uDCC3';
}

function fileDetail(file: UploadedFile, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (file.type === 'directory') return `${file.file_count ?? 0} ${t('documents.files')}`;
  return formatSize(file.size);
}

export function DocumentList({ files, onDelete, className = '' }: DocumentListProps): JSX.Element {
  const { t } = useTranslation();

  if (files.length === 0) return <></>;

  return (
    <ul className={`divide-y divide-border rounded-lg border border-border ${className}`}>
      {files.map((file) => (
        <li key={file.name} className="flex items-center gap-3 px-3 py-2">
          <span className="text-lg">{fileIcon(file)}</span>
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-medium text-content-primary">{file.name}</p>
            <p className="text-xs text-content-tertiary">{fileDetail(file, t)}</p>
          </div>
          {onDelete && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete(file.name)}
              title={t('common.delete')}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}
