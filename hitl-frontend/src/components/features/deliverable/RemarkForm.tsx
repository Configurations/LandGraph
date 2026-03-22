import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';

interface RemarkFormProps {
  onSubmit: (comment: string) => void;
  loading?: boolean;
  className?: string;
}

export function RemarkForm({
  onSubmit,
  loading = false,
  className = '',
}: RemarkFormProps): JSX.Element {
  const { t } = useTranslation();
  const [comment, setComment] = useState('');

  const handleSubmit = () => {
    const trimmed = comment.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setComment('');
  };

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder={t('deliverable.remark_placeholder')}
        rows={3}
        className="w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-sm text-content-primary placeholder:text-content-quaternary focus:border-accent-blue focus:outline-none focus:ring-1 focus:ring-accent-blue resize-none"
      />
      <Button
        size="sm"
        variant="secondary"
        onClick={handleSubmit}
        loading={loading}
        disabled={!comment.trim()}
      >
        {t('deliverable.submit_remark')}
      </Button>
    </div>
  );
}
