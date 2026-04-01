import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/Badge';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import type { AnalysisMessage } from '../../../api/types';

interface AnalysisChatMessageProps {
  message: AnalysisMessage;
  onReply?: (requestId: string, response: string) => void;
  className?: string;
}

/** Parse numbered questions from a ```? ... ``` block, with fallback to inline numbered lines. */
function parseQuestions(text: string): { intro: string; questions: { text: string; choices: string[] }[] } | null {
  // Priority 1: explicit (((?  ... ))) block
  const blockMatch = text.match(/\(\(\(\?\s*\n([\s\S]*?)\)\)\)/);
  if (blockMatch) {
    const intro = text.slice(0, text.indexOf('(((?')).trim();
    return parseNumberedLines(intro, blockMatch[1]);
  }

  // Priority 2: fallback — numbered lines anywhere in the text
  const normalized = text.replace(/\s+(\d+)[.)]\s+/g, '\n$1. ');
  const firstNum = normalized.search(/^\s*\d+[.)]\s+/m);
  if (firstNum < 0) return null;
  const intro = normalized.slice(0, firstNum).trim();
  const body = normalized.slice(firstNum);
  return parseNumberedLines(intro, body);
}

function parseNumberedLines(intro: string, body: string): { intro: string; questions: { text: string; choices: string[] }[] } | null {
  const lines = body.split('\n');
  const questions: { text: string; choices: string[] }[] = [];
  let currentQ = '';

  for (const line of lines) {
    const match = line.match(/^\s*(\d+)[.)]\s+(.+)/);
    if (match) {
      if (currentQ) questions.push(parseChoices(currentQ));
      currentQ = match[2];
    } else if (currentQ && line.trim()) {
      currentQ += ' ' + line.trim();
    }
  }
  if (currentQ) questions.push(parseChoices(currentQ));

  return questions.length > 0 ? { intro, questions } : null;
}

function parseChoices(text: string): { text: string; choices: string[] } {
  // Detect choices in parentheses: (MVP, feature, bugs) or (ex: MVP, feature)
  const match = text.match(/\((?:ex\s*:\s*)?([^)]+)\)\s*[?]?\s*$/);
  if (match) {
    const choicesStr = match[1];
    const choices = choicesStr.split(/[,;]/).map(c => c.trim()).filter(c => c.length > 0 && c.length < 60);
    if (choices.length >= 2 && choices.length <= 8) {
      const questionText = text.slice(0, text.indexOf('(' + match[1])).trim();
      return { text: questionText || text, choices };
    }
  }
  return { text, choices: [] };
}

export function AnalysisChatMessage({ message, onReply, className = '' }: AnalysisChatMessageProps): JSX.Element {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [answers, setAnswers] = useState<Record<number, string | string[]>>({});
  const [otherText, setOtherText] = useState<Record<number, string>>({});
  const [sent, setSent] = useState(false);
  const time = new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (message.type === 'system') {
    return (
      <p className={`text-center text-xs italic text-content-quaternary py-1 ${className}`}>
        {message.content}
      </p>
    );
  }

  const isUser = message.sender === 'user';
  const isQuestion = message.type === 'question';
  const isArtifact = message.type === 'artifact';
  const isResult = message.type === 'result';
  const isPending = isQuestion && message.status === 'pending';

  // Parse questions for interactive cards
  const parsed = isQuestion && isPending && !sent ? parseQuestions(message.content) : null;

  const agentName = message.agent_id || 'Agent';
  const avatarUrl = message.agent_avatar || undefined;

  const answeredCount = Object.keys(answers).length;
  const totalQuestions = parsed?.questions.length ?? 0;

  const handleChipSelect = useCallback((qIdx: number, choice: string, multi: boolean) => {
    setAnswers(prev => {
      const current = prev[qIdx];
      if (multi) {
        const arr = Array.isArray(current) ? [...current] : [];
        const idx = arr.indexOf(choice);
        if (idx >= 0) arr.splice(idx, 1);
        else arr.push(choice);
        return { ...prev, [qIdx]: arr.length > 0 ? arr : [] };
      }
      return { ...prev, [qIdx]: current === choice ? '' : choice };
    });
  }, []);

  const handleTextAnswer = useCallback((qIdx: number, value: string) => {
    setAnswers(prev => ({ ...prev, [qIdx]: value }));
  }, []);

  const handleSendAll = useCallback(() => {
    if (!parsed || !onReply || !message.request_id) return;
    const parts: string[] = [];
    parsed.questions.forEach((_q, i) => {
      const a = answers[i];
      let text = Array.isArray(a) ? a.join(', ') : (a || '');
      // Replace "Autre" chip with the custom text
      if (text === 'Autre' || (Array.isArray(a) && a.includes('Autre'))) {
        const custom = otherText[i] || '';
        if (Array.isArray(a)) {
          const withoutAutre = a.filter(v => v !== 'Autre');
          if (custom) withoutAutre.push(custom);
          text = withoutAutre.join(', ');
        } else {
          text = custom;
        }
      }
      if (text) parts.push(`${i + 1}. ${text}`);
    });
    if (parts.length > 0) {
      onReply(message.request_id, parts.join('\n'));
      setSent(true);
    }
  }, [parsed, answers, otherText, onReply, message.request_id]);

  const hasAnswers = Object.entries(answers).some(([key, a]) => {
    const idx = Number(key);
    if (Array.isArray(a)) {
      if (a.length === 1 && a[0] === 'Autre') return !!(otherText[idx] || '').trim();
      return a.length > 0;
    }
    if (a === 'Autre') return !!(otherText[idx] || '').trim();
    return typeof a === 'string' && a.trim().length > 0;
  });

  return (
    <div className={`flex max-w-[85%] gap-2 ${isUser ? 'self-end flex-row-reverse' : 'self-start'} ${className}`}>
      {!isUser && (
        avatarUrl
          ? <img src={avatarUrl} alt={agentName} className="w-16 h-16 rounded-full flex-shrink-0 mt-1 object-cover" />
          : <Avatar name={agentName} size="md" className="flex-shrink-0 mt-1" />
      )}
      <div className="flex flex-col gap-1 flex-1">
        {/* Agent name */}
        {!isUser && message.agent_id && (
          <span className="text-[10px] font-semibold text-accent-blue px-1">{agentName}</span>
        )}

        {/* Question with interactive cards */}
        {parsed && !sent ? (
          <div className="flex flex-col gap-1.5">
            {parsed.intro && (
              <div className="rounded-lg px-3 py-2 text-sm bg-surface-tertiary">
                <MarkdownRenderer content={parsed.intro} />
              </div>
            )}
            {/* Progress */}
            <div className="flex items-center gap-2 px-1">
              <Badge size="sm" color="orange">{totalQuestions} question{totalQuestions > 1 ? 's' : ''}</Badge>
              <div className="flex gap-1">
                {parsed.questions.map((_, i) => {
                  const a = answers[i];
                  const filled = Array.isArray(a) ? a.length > 0 : (typeof a === 'string' && a.trim().length > 0);
                  return <div key={i} className={`w-1.5 h-1.5 rounded-full ${filled ? 'bg-green-500' : 'bg-border'}`} />;
                })}
              </div>
              <span className="text-[10px] text-content-quaternary">{answeredCount}/{totalQuestions}</span>
            </div>

            {/* Question cards */}
            {parsed.questions.map((q, i) => {
              const a = answers[i];
              const selectedChips = Array.isArray(a) ? a : (typeof a === 'string' && q.choices.includes(a) ? [a] : []);
              const isMulti = q.text.toLowerCase().includes('plusieurs') || q.text.toLowerCase().includes('prioriser');

              return (
                <div key={i} className="bg-surface-primary border border-border border-l-2 border-l-accent-orange rounded-lg overflow-hidden">
                  <div className="px-3 py-2 text-xs text-content-primary">{i + 1}. {q.text}</div>
                  {q.choices.length > 0 ? (
                    <div className="px-3 pb-2 flex flex-col gap-1.5">
                      <div className="flex flex-wrap gap-1.5">
                        {isMulti && <div className="w-full text-[9px] text-content-quaternary italic mb-0.5">Plusieurs choix possibles</div>}
                        {q.choices.map(choice => (
                          <button
                            key={choice}
                            onClick={() => handleChipSelect(i, choice, isMulti)}
                            className={[
                              'px-2.5 py-1 rounded-full text-[11px] border transition-all',
                              selectedChips.includes(choice)
                                ? 'bg-accent-blue/15 border-accent-blue text-accent-blue'
                                : 'bg-surface-secondary border-border text-content-tertiary hover:border-accent-blue/50',
                            ].join(' ')}
                          >
                            {selectedChips.includes(choice) && '✓ '}{choice}
                          </button>
                        ))}
                        <button
                          onClick={() => handleChipSelect(i, 'Autre', isMulti)}
                          className={[
                            'px-2.5 py-1 rounded-full text-[11px] border transition-all italic',
                            selectedChips.includes('Autre')
                              ? 'bg-accent-orange/15 border-accent-orange text-accent-orange'
                              : 'bg-surface-secondary border-border text-content-quaternary hover:border-accent-orange/50',
                          ].join(' ')}
                        >
                          {selectedChips.includes('Autre') && '✓ '}Autre
                        </button>
                      </div>
                      {selectedChips.includes('Autre') && (
                        <textarea
                          rows={2}
                          placeholder="Precisez..."
                          value={otherText[i] || ''}
                          onChange={e => setOtherText(prev => ({ ...prev, [i]: e.target.value }))}
                          className="w-full bg-surface-secondary border border-border rounded-lg px-2.5 py-1.5 text-xs text-content-primary resize-y outline-none focus:border-accent-orange"
                        />
                      )}
                    </div>
                  ) : (
                    <div className="px-3 pb-2">
                      <textarea
                        rows={2}
                        placeholder="Votre reponse..."
                        value={typeof a === 'string' ? a : ''}
                        onChange={e => handleTextAnswer(i, e.target.value)}
                        className="w-full bg-surface-secondary border border-border rounded-lg px-2.5 py-1.5 text-xs text-content-primary resize-y outline-none focus:border-accent-blue"
                      />
                    </div>
                  )}
                </div>
              );
            })}

            <button
              disabled={!hasAnswers}
              onClick={handleSendAll}
              className={[
                'self-end px-4 py-1.5 rounded-lg text-xs font-semibold transition-all',
                hasAnswers
                  ? 'bg-accent-blue text-white hover:opacity-90'
                  : 'bg-surface-tertiary text-content-quaternary cursor-not-allowed',
              ].join(' ')}
            >
              {totalQuestions > 1 ? 'Envoyer les reponses' : 'Repondre'}
            </button>
          </div>
        ) : (
          /* Standard message rendering */
          <div
            className={[
              'rounded-lg px-3 py-2 text-sm',
              isUser ? 'bg-accent-blue/20 text-content-primary' : 'bg-surface-tertiary text-content-primary',
              isPending && !parsed ? 'border border-accent-orange' : '',
              sent ? 'border border-green-500/30' : '',
            ].join(' ')}
          >
            {isQuestion && !sent && (
              <div className="flex items-center gap-1.5 mb-1">
                <Badge size="sm" color="orange">{t('analysis.question_badge')}</Badge>
                {isPending && <span className="h-2 w-2 rounded-full bg-accent-orange animate-pulse" />}
              </div>
            )}
            {sent && (
              <div className="flex items-center gap-1.5 mb-1">
                <Badge size="sm" color="green">Repondu</Badge>
              </div>
            )}
            {isResult && (
              <Badge size="sm" color={message.content.includes('fail') ? 'red' : 'green'} className="mb-1">
                {message.content.includes('fail') ? t('analysis.failed') : t('analysis.completed')}
              </Badge>
            )}
            {isArtifact ? (
              <div>
                <Badge size="sm" color="purple" className="mb-1">{t('analysis.artifact_badge')}</Badge>
                <div className={expanded ? '' : 'max-h-[300px] overflow-hidden'}>
                  <MarkdownRenderer content={message.content} />
                </div>
                {message.content.length > 500 && (
                  <button
                    onClick={() => setExpanded(!expanded)}
                    className="text-xs text-accent-blue mt-1 hover:underline"
                  >
                    {expanded ? '\u25B2' : '\u25BC'}
                  </button>
                )}
              </div>
            ) : (
              <MarkdownRenderer content={message.content} />
            )}
          </div>
        )}

        <span className={`text-[10px] text-content-quaternary px-1 ${isUser ? 'text-right' : ''}`}>
          {time}
        </span>
      </div>
    </div>
  );
}
