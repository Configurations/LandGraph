import { create } from 'zustand';
import * as chatApi from '../api/chat';
import type { ChatMessage } from '../api/types';

interface ChatState {
  messages: ChatMessage[];
  activeAgentId: string | null;
  loading: boolean;
  loadHistory: (teamId: string, agentId: string) => Promise<void>;
  addMessage: (message: ChatMessage) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  activeAgentId: null,
  loading: false,

  loadHistory: async (teamId: string, agentId: string) => {
    set({ loading: true, activeAgentId: agentId });
    try {
      const messages = await chatApi.getChatHistory(teamId, agentId);
      set({ messages, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  addMessage: (message: ChatMessage) =>
    set((state) => ({ messages: [...state.messages, message] })),

  clearMessages: () => set({ messages: [], activeAgentId: null }),
}));
