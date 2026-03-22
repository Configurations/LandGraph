import { useCallback, useEffect, useRef } from 'react';
import { getToken } from '../api/client';
import type { WebSocketEvent } from '../api/types';
import { useNotificationStore } from '../stores/notificationStore';
import { useAuthStore } from '../stores/authStore';
import { useWsStore } from '../stores/wsStore';

const MIN_BACKOFF = 5000;
const MAX_BACKOFF = 30000;
const MAX_RETRIES = 10;

export function useWebSocket(teamId: string | null): void {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const backoffRef = useRef(MIN_BACKOFF);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setConnected = useWsStore((s) => s.setConnected);
  const setLastEvent = useWsStore((s) => s.setLastEvent);
  const incrementPending = useNotificationStore((s) => s.incrementPending);
  const logout = useAuthStore((s) => s.logout);

  const connect = useCallback(() => {
    if (!teamId) return;

    const token = getToken();
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/api/teams/${teamId}/ws?token=${token}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      retriesRef.current = 0;
      backoffRef.current = MIN_BACKOFF;
    };

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data as string) as WebSocketEvent;
        setLastEvent(parsed);
        if (parsed.type === 'new_question') {
          incrementPending();
        }
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = (event) => {
      setConnected(false);
      wsRef.current = null;

      if (event.code === 4001 || event.code === 4003) {
        logout();
        return;
      }

      if (retriesRef.current < MAX_RETRIES) {
        reconnectTimer.current = setTimeout(() => {
          retriesRef.current += 1;
          backoffRef.current = Math.min(backoffRef.current * 1.5, MAX_BACKOFF);
          connect();
        }, backoffRef.current);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [teamId, setConnected, setLastEvent, incrementPending, logout]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
    };
  }, [connect, setConnected]);
}
