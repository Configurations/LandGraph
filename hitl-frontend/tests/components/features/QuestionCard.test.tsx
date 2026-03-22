import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuestionCard } from '../../../src/components/features/hitl/QuestionCard';
import type { QuestionResponse } from '../../../src/api/types';

function makeQuestion(overrides: Partial<QuestionResponse> = {}): QuestionResponse {
  return {
    id: 'q-1',
    thread_id: 'thread-1',
    agent_name: 'Lead Dev',
    agent_id: 'lead_dev',
    team_id: 'team1',
    question_type: 'question',
    prompt: 'Should we use React or Vue?',
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

describe('QuestionCard', () => {
  it('renders question prompt', () => {
    render(<QuestionCard question={makeQuestion()} />);
    expect(screen.getByText('Should we use React or Vue?')).toBeInTheDocument();
  });

  it('shows agent name', () => {
    render(<QuestionCard question={makeQuestion()} />);
    expect(screen.getByText('Lead Dev')).toBeInTheDocument();
  });

  it('shows status badge', () => {
    render(<QuestionCard question={makeQuestion({ status: 'pending' })} />);
    expect(screen.getByText('hitl.pending')).toBeInTheDocument();
  });

  it('shows urgency indicator for pending questions', () => {
    const { container } = render(<QuestionCard question={makeQuestion({ status: 'pending' })} />);
    const pulse = container.querySelector('.animate-pulse');
    expect(pulse).toBeTruthy();
  });

  it('no urgency indicator for answered questions', () => {
    const { container } = render(<QuestionCard question={makeQuestion({ status: 'answered' })} />);
    const pulse = container.querySelector('.animate-pulse');
    expect(pulse).toBeNull();
  });

  it('renders approve/reject buttons for pending approvals', () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <QuestionCard
        question={makeQuestion({ question_type: 'approval', status: 'pending' })}
        onApprove={onApprove}
        onReject={onReject}
      />,
    );
    expect(screen.getByText('hitl.approve')).toBeInTheDocument();
    expect(screen.getByText('hitl.reject')).toBeInTheDocument();
  });

  it('does not render approve/reject for non-approval type', () => {
    render(
      <QuestionCard
        question={makeQuestion({ question_type: 'question', status: 'pending' })}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );
    expect(screen.queryByText('hitl.approve')).toBeNull();
    expect(screen.queryByText('hitl.reject')).toBeNull();
  });

  it('calls onApprove when approve button clicked', () => {
    const onApprove = vi.fn();
    render(
      <QuestionCard
        question={makeQuestion({ question_type: 'approval', status: 'pending' })}
        onApprove={onApprove}
      />,
    );
    fireEvent.click(screen.getByText('hitl.approve'));
    expect(onApprove).toHaveBeenCalledOnce();
  });

  it('shows team_id and channel badges', () => {
    render(<QuestionCard question={makeQuestion()} />);
    expect(screen.getByText('team1')).toBeInTheDocument();
    expect(screen.getByText('discord')).toBeInTheDocument();
  });
});
