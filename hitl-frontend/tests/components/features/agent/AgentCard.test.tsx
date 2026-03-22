import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentCard } from '../../../../src/components/features/agent/AgentCard';
import type { AgentInfo } from '../../../../src/api/types';

function makeAgent(overrides: Partial<AgentInfo> = {}): AgentInfo {
  return {
    id: 'lead_dev', name: 'Lead Dev', llm: 'claude-sonnet',
    type: 'lead', pending_questions: 0,
    ...overrides,
  };
}

describe('AgentCard', () => {
  it('renders name and LLM', () => {
    render(<AgentCard agent={makeAgent()} teamId="team1" />);
    expect(screen.getByText('Lead Dev')).toBeInTheDocument();
    expect(screen.getByText('claude-sonnet')).toBeInTheDocument();
  });

  it('shows pending count badge when > 0', () => {
    render(<AgentCard agent={makeAgent({ pending_questions: 3 })} teamId="team1" />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('does not show pending badge when 0', () => {
    render(<AgentCard agent={makeAgent({ pending_questions: 0 })} teamId="team1" />);
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('shows type badge', () => {
    render(<AgentCard agent={makeAgent({ type: 'orchestrator' })} teamId="team1" />);
    // t() returns the key in tests
    expect(screen.getByText('agent.type_orchestrator')).toBeInTheDocument();
  });
});
