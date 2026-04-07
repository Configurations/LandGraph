import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/Button';
import type { HumanGateInfo } from '../../../api/types';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';

interface Props {
  gate: HumanGateInfo;
  onRespond: (response: string) => Promise<void>;
}

export function HumanGateBanner({ gate, onRespond }: Props): JSX.Element {
  const { t } = useTranslation();
  const [response, setResponse] = useState('');
  const [sending, setSending] = useState(false);

  const handleSubmit = async () => {
    if (!response.trim()) return;
    setSending(true);
    try {
      await onRespond(response);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="rounded-lg border-2 border-accent-orange bg-accent-orange/5 p-4 mb-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">&#9888;</span>
        <span className="font-semibold text-sm text-accent-orange">{t('workflow.human_gate')}</span>
        <span className="text-xs text-content-tertiary ml-auto">{gate.agent_id}</span>
      </div>
      <div className="text-sm mb-3">
        <MarkdownRenderer content={gate.prompt} />
      </div>
      <div className="flex gap-2">
        <textarea
          rows={2}
          className="flex-1 rounded border border-border bg-surface-primary px-3 py-2 text-sm"
          placeholder={t('workflow.gate_response_placeholder')}
          value={response}
          onChange={(e) => setResponse(e.target.value)}
        />
        <Button onClick={() => void handleSubmit()} loading={sending} disabled={!response.trim()}>
          {t('workflow.respond')}
        </Button>
      </div>
    </div>
  );
}
