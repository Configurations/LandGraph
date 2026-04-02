/** Shared question parser — extracts structured questions from agent messages. */

export interface ParsedQuestion {
  text: string;
  choices: string[];
}

export interface ParsedQuestions {
  intro: string;
  questions: ParsedQuestion[];
}

/** Parse numbered questions from a (((? ... ))) block, with fallback to inline numbered lines. */
export function parseQuestions(text: string): ParsedQuestions | null {
  // Priority 1: explicit (((? ... ))) block
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

function parseNumberedLines(intro: string, body: string): ParsedQuestions | null {
  const lines = body.split('\n');
  const questions: ParsedQuestion[] = [];
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

function parseChoices(text: string): ParsedQuestion {
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

/** Strip (((? ... ))) markers from text for plain display. */
export function stripQuestionMarkers(text: string): string {
  return text.replace(/\(\(\(\?\s*\n?/g, '').replace(/\)\)\)/g, '').trim();
}
