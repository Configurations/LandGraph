import { useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';

interface ChatInputProps {
  onSend: (message: string) => void;
  loading?: boolean;
  placeholder?: string;
  className?: string;
}

export function ChatInput({
  onSend,
  loading = false,
  placeholder,
  className = '',
}: ChatInputProps): JSX.Element {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={`relative flex items-end gap-2 border-t border-border p-3 pb-5 ${className}`}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder ?? t('chat.input_placeholder')}
        rows={1}
        className="flex-1 resize-none rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-sm text-content-primary placeholder:text-content-quaternary focus:border-accent-blue focus:outline-none focus:ring-1 focus:ring-accent-blue"
      />
      <Button
        size="sm"
        onClick={handleSend}
        loading={loading}
        disabled={!value.trim()}
      >
        {t('chat.send')}
      </Button>
      <span className="absolute bottom-0.5 left-3 text-[10px] text-content-quaternary">
        {t('analysis.ctrl_enter_hint')}
      </span>
    </div>
  );
}
