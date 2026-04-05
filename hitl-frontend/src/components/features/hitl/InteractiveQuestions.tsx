import { useState, useCallback } from 'react';
import { Badge } from '../../ui/Badge';
import { MarkdownRenderer } from '../deliverable/MarkdownRenderer';
import type { ParsedQuestions } from '../../../utils/questionParser';

interface InteractiveQuestionsProps {
  parsed: ParsedQuestions;
  onSubmit: (response: string) => void;
  intro?: boolean;
  className?: string;
}

/**
 * Renders parsed questions as interactive cards with chips, "Autre" option, and text inputs.
 * Used by AnalysisChatMessage (chat) and AnswerModal (inbox).
 */
export function InteractiveQuestions({ parsed, onSubmit, intro = true, className = '' }: InteractiveQuestionsProps): JSX.Element {
  const [answers, setAnswers] = useState<Record<number, string | string[]>>({});
  const [otherText, setOtherText] = useState<Record<number, string>>({});

  const totalQuestions = parsed.questions.length;
  const answeredCount = Object.keys(answers).length;

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
    const parts: string[] = [];
    parsed.questions.forEach((_q, i) => {
      const a = answers[i];
      let text = Array.isArray(a) ? a.join(', ') : (a || '');
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
      onSubmit(parts.join('\n\n'));
    }
  }, [parsed, answers, otherText, onSubmit]);

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
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {intro && parsed.intro && (
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
        const selectedChips = Array.isArray(a) ? a : (typeof a === 'string' && (q.choices.includes(a) || a === 'Autre') ? [a] : []);
        const isMulti = q.choices.length > 0;

        return (
          <div key={i} className="bg-surface-primary border border-border border-l-2 border-l-accent-orange rounded-lg overflow-hidden">
            <div className="px-3 py-2 text-xs text-content-primary">{i + 1}. {q.text}</div>
            {q.choices.length > 0 ? (
              <div className="px-3 pb-2 flex flex-col gap-1.5">
                <div className="flex flex-wrap gap-1.5">
                  <div className="w-full text-[9px] text-content-quaternary italic mb-0.5">Plusieurs choix possibles</div>
                  {q.choices.map(choice => (
                    <button
                      key={choice}
                      onClick={() => handleChipSelect(i, choice, isMulti)}
                      className={[
                        'px-3 py-1.5 rounded-full text-xs font-medium border transition-all',
                        selectedChips.includes(choice)
                          ? 'bg-accent-blue/15 border-accent-blue text-accent-blue'
                          : 'bg-surface-secondary border-border text-content-secondary hover:border-accent-blue/50',
                      ].join(' ')}
                    >
                      {selectedChips.includes(choice) && '✓ '}{choice}
                    </button>
                  ))}
                  <button
                    onClick={() => handleChipSelect(i, 'Autre', isMulti)}
                    className={[
                      'px-3 py-1.5 rounded-full text-xs font-medium border transition-all italic',
                      selectedChips.includes('Autre')
                        ? 'bg-accent-orange/15 border-accent-orange text-accent-orange'
                        : 'bg-surface-secondary border-border text-content-secondary hover:border-accent-orange/50',
                    ].join(' ')}
                  >
                    {selectedChips.includes('Autre') && '✓ '}Autre
                  </button>
                </div>
                {selectedChips.includes('Autre') && (
                  <textarea
                    rows={4}
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
                  rows={4}
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
  );
}
