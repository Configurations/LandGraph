import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ChatBubble } from '../../../../src/components/features/chat/ChatBubble';
import type { ChatMessage } from '../../../../src/api/types';

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: '1', team_id: 'team1', agent_id: 'lead_dev',
    thread_id: 'hitl-chat-team1-lead_dev',
    sender: 'alice@t.com', content: 'Hello agent',
    created_at: '2026-03-20T10:00:00Z',
    ...overrides,
  };
}

describe('ChatBubble', () => {
  it('user message is right-aligned', () => {
    const { container } = render(
      <ChatBubble message={makeMessage()} isUser={true} />,
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('self-end');
  });

  it('agent message is left-aligned', () => {
    const { container } = render(
      <ChatBubble message={makeMessage({ sender: 'lead_dev' })} isUser={false} />,
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('self-start');
  });

  it('renders content', () => {
    const { container } = render(
      <ChatBubble message={makeMessage({ content: 'Test message' })} isUser={true} />,
    );
    expect(container.textContent).toContain('Test message');
  });

  it('shows avatar for agent messages', () => {
    const { container } = render(
      <ChatBubble
        message={makeMessage({ sender: 'lead_dev' })}
        isUser={false}
        agentName="Lead Dev"
        agentAvatarUrl="/avatars/cyberpunk/lead_dev.1.png"
      />,
    );
    const img = container.querySelector('img');
    expect(img).toBeTruthy();
    expect(img?.getAttribute('src')).toBe('/avatars/cyberpunk/lead_dev.1.png');
  });

  it('does not show avatar for user messages', () => {
    const { container } = render(
      <ChatBubble
        message={makeMessage()}
        isUser={true}
        agentName="Lead Dev"
        agentAvatarUrl="/avatars/cyberpunk/lead_dev.1.png"
      />,
    );
    const img = container.querySelector('img');
    expect(img).toBeNull();
  });
});
