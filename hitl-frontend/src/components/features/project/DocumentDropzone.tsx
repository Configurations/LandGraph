import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useTranslation } from 'react-i18next';
import { Spinner } from '../../ui/Spinner';

interface DocumentDropzoneProps {
  onUpload: (file: File) => void;
  uploading: boolean;
  className?: string;
}

const ACCEPT_MAP: Record<string, string[]> = {
  'text/markdown': ['.md'],
  'text/plain': ['.txt'],
  'application/pdf': ['.pdf'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
};

export function DocumentDropzone({ onUpload, uploading, className = '' }: DocumentDropzoneProps): JSX.Element {
  const { t } = useTranslation();

  const onDrop = useCallback(
    (accepted: File[]) => {
      const first = accepted[0];
      if (first) onUpload(first);
    },
    [onUpload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT_MAP,
    multiple: false,
    disabled: uploading,
  });

  return (
    <div
      {...getRootProps()}
      className={[
        'flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors',
        isDragActive ? 'border-accent-blue bg-accent-blue/10' : 'border-border hover:border-content-quaternary',
        uploading ? 'opacity-50 cursor-not-allowed' : '',
        className,
      ].join(' ')}
    >
      <input {...getInputProps()} />
      {uploading ? (
        <>
          <Spinner size="md" />
          <p className="text-sm text-content-secondary">{t('documents.uploading')}</p>
        </>
      ) : (
        <>
          <svg className="h-8 w-8 text-content-quaternary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 16V4m0 0l-4 4m4-4l4 4M4 14v4a2 2 0 002 2h12a2 2 0 002-2v-4" />
          </svg>
          <p className="text-sm text-content-secondary text-center">{t('documents.dropzone')}</p>
          <p className="text-xs text-content-quaternary">{t('documents.accepted_formats')}</p>
        </>
      )}
    </div>
  );
}
