import { apiFetch } from './client';
import type {
  AnswerPayload,
  QuestionListParams,
  QuestionResponse,
  QuestionStatsResponse,
} from './types';

export function listQuestions(
  teamId: string,
  params: QuestionListParams = {},
): Promise<QuestionResponse[]> {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.channel) query.set('channel', params.channel);
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.offset !== undefined) query.set('offset', String(params.offset));
  const qs = query.toString();
  const url = `/api/teams/${encodeURIComponent(teamId)}/questions${qs ? `?${qs}` : ''}`;
  return apiFetch<QuestionResponse[]>(url);
}

export function getQuestionStats(teamId: string): Promise<QuestionStatsResponse> {
  return apiFetch<QuestionStatsResponse>(
    `/api/teams/${encodeURIComponent(teamId)}/questions/stats`,
  );
}

export function answerQuestion(
  questionId: string,
  payload: AnswerPayload,
): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `/api/questions/${encodeURIComponent(questionId)}/answer`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}
