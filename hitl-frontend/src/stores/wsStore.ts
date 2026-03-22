import { create } from 'zustand';
import type { WebSocketEvent } from '../api/types';

interface WsState {
  connected: boolean;
  lastEvent: WebSocketEvent | null;
  setConnected: (connected: boolean) => void;
  setLastEvent: (event: WebSocketEvent) => void;
}

export const useWsStore = create<WsState>((set) => ({
  connected: false,
  lastEvent: null,
  setConnected: (connected) => set({ connected }),
  setLastEvent: (event) => set({ lastEvent: event }),
}));
