import { create } from 'zustand';

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  messageKey: string;
  params?: Record<string, string>;
  createdAt: number;
}

interface NotificationState {
  toasts: Toast[];
  pendingCount: number;
  addToast: (type: Toast['type'], messageKey: string, params?: Record<string, string>) => void;
  removeToast: (id: string) => void;
  setPendingCount: (n: number) => void;
  incrementPending: () => void;
  decrementPending: () => void;
}

let toastCounter = 0;

export const useNotificationStore = create<NotificationState>((set) => ({
  toasts: [],
  pendingCount: 0,

  addToast: (type, messageKey, params) => {
    const id = `toast-${++toastCounter}-${Date.now()}`;
    const toast: Toast = { id, type, messageKey, params, createdAt: Date.now() };
    set((state) => ({ toasts: [...state.toasts, toast] }));
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
    }, 4000);
  },

  removeToast: (id) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },

  setPendingCount: (n) => set({ pendingCount: n }),
  incrementPending: () => set((state) => ({ pendingCount: state.pendingCount + 1 })),
  decrementPending: () =>
    set((state) => ({ pendingCount: Math.max(0, state.pendingCount - 1) })),
}));
