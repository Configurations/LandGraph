import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { InboxPage } from '../../src/pages/InboxPage';
import { useTeamStore } from '../../src/stores/teamStore';
import { useNotificationStore } from '../../src/stores/notificationStore';
import { useWsStore } from '../../src/stores/wsStore';
import type { QuestionResponse } from '../../src/api/types';

// Mock hitl API
vi.mock('../../src/api/hitl', () => ({
  listQuestions: vi.fn(),
  answerQuestion: vi.fn(),
}));

// Mock AnswerModal to simplify rendering
vi.mock('../../src/components/features/hitl/AnswerModal', () => ({
  AnswerModal: () => null,
}));

function makeQuestion(overrides: Partial<QuestionResponse> = {}): QuestionResponse {
  return {
    id: `q-${Math.random()}`,
    thread_id: 'thread-1',
    agent_name: 'Architect',
    agent_id: 'architect',
    team_id: 'team1',
    question_type: 'question',
    prompt: 'Choose database?',
    context: '',
    status: 'pending',
    response: null,
    reviewer: null,
    channel: 'discord',
    created_at: new Date().toISOString(),
    answered_at: null,
    ...overrides,
  };
}

describe('InboxPage', () => {
  beforeEach(() => {
    useTeamStore.setState({
      teams: [{ id: 'team1', name: 'Team 1', directory: 'T1' }],
      activeTeamId: 'team1',
    });
    useNotificationStore.setState({ pendingCount: 0, toasts: [] });
    useWsStore.setState({ connected: false, lastEvent: null });
  });

  it('renders question list', async () => {
    const hitlApi = await import('../../src/api/hitl');
    (hitlApi.listQuestions as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeQuestion({ prompt: 'Pick a framework' }),
      makeQuestion({ prompt: 'Which ORM?' }),
    ]);

    render(<InboxPage />);

    await waitFor(() => {
      expect(screen.getByText('Pick a framework')).toBeInTheDocument();
      expect(screen.getByText('Which ORM?')).toBeInTheDocument();
    });
  });

  it('shows empty state when no questions', async () => {
    const hitlApi = await import('../../src/api/hitl');
    (hitlApi.listQuestions as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    render(<InboxPage />);

    await waitFor(() => {
      expect(screen.getByText('hitl.no_pending')).toBeInTheDocument();
    });
  });

  it('renders filter controls', async () => {
    const hitlApi = await import('../../src/api/hitl');
    (hitlApi.listQuestions as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    render(<InboxPage />);

    await waitFor(() => {
      expect(screen.getByText('hitl.questions')).toBeInTheDocument();
    });
  });

  it('shows pending badge when there are pending questions', async () => {
    const hitlApi = await import('../../src/api/hitl');
    (hitlApi.listQuestions as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeQuestion({ status: 'pending' }),
      makeQuestion({ status: 'pending' }),
      makeQuestion({ status: 'answered' }),
    ]);

    render(<InboxPage />);

    await waitFor(() => {
      const badges = screen.getAllByText('2');
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });
  });
});
