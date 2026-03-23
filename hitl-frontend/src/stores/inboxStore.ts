import { create } from 'zustand';
import * as inboxApi from '../api/inbox';
import type { PMNotification } from '../api/types';

interface InboxState {
  notifications: PMNotification[];
  unreadCount: number;
  loading: boolean;
  loadNotifications: () => Promise<void>;
  markAsRead: (id: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  loadUnreadCount: () => Promise<void>;
}

export const useInboxStore = create<InboxState>((set) => ({
  notifications: [],
  unreadCount: 0,
  loading: false,

  loadNotifications: async () => {
    set({ loading: true });
    try {
      const notifications = await inboxApi.listNotifications();
      const unreadCount = notifications.filter((n) => !n.read).length;
      set({ notifications, unreadCount, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  markAsRead: async (id: string) => {
    await inboxApi.markRead(id);
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n,
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    }));
  },

  markAllAsRead: async () => {
    await inboxApi.markAllRead();
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }));
  },

  loadUnreadCount: async () => {
    try {
      const count = await inboxApi.getUnreadCount();
      set({ unreadCount: count });
    } catch {
      // silent
    }
  },
}));
