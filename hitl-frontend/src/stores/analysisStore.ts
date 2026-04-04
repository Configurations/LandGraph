import { create } from 'zustand';
import type { AnalysisMessage } from '../api/types';

type AnalysisUiStatus = 'idle' | 'starting' | 'running' | 'waiting_input' | 'completed' | 'failed';

interface PendingQuestion {
  requestId: string;
  prompt: string;
}

interface AnalysisState {
  status: AnalysisUiStatus;
  taskId: string | null;
  workflowId: number | null;
  threadId: string | null;
  messages: AnalysisMessage[];
  pendingQuestion: PendingQuestion | null;

  setStatus: (s: AnalysisUiStatus) => void;
  setTaskId: (id: string | null) => void;
  setWorkflowId: (id: number | null) => void;
  setThreadId: (id: string | null) => void;
  addMessage: (msg: AnalysisMessage) => void;
  setMessages: (msgs: AnalysisMessage[]) => void;
  setPendingQuestion: (q: PendingQuestion | null) => void;
  reset: () => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  status: 'idle',
  taskId: null,
  workflowId: null,
  threadId: null,
  messages: [],
  pendingQuestion: null,

  setStatus: (status) => set({ status }),
  setTaskId: (taskId) => set({ taskId }),
  setWorkflowId: (workflowId) => set({ workflowId }),
  setThreadId: (threadId) => set({ threadId }),
  addMessage: (msg) =>
    set((s) => {
      if (s.messages.some((m) => m.id === msg.id)) return s;
      return { messages: [...s.messages, msg] };
    }),
  setMessages: (messages) => set({ messages }),
  setPendingQuestion: (pendingQuestion) => set({ pendingQuestion }),
  reset: () =>
    set({ status: 'idle', taskId: null, workflowId: null, threadId: null, messages: [], pendingQuestion: null }),
}));
