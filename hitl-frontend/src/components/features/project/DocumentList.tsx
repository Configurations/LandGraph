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

function fileIcon(contentType: string): string {
  if (contentType.startsWith('image/')) return '\uD83D\uDDBC';
  if (contentType === 'application/pdf') return '\uD83D\uDCC4';
  return '\uD83D\uDCC3';
}

export function DocumentList({ files, onDelete, className = '' }: DocumentListProps): JSX.Element {
  const { t } = useTranslation();

  if (files.length === 0) return <></>;

  return (
    <ul className={`divide-y divide-border rounded-lg border border-border ${className}`}>
      {files.map((file) => (
        <li key={file.name} className="flex items-center gap-3 px-3 py-2">
          <span className="text-lg">{fileIcon(file.content_type)}</span>
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-medium text-content-primary">{file.name}</p>
            <p className="text-xs text-content-tertiary">{formatSize(file.size)}</p>
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
