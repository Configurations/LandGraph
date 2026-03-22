import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWsStore } from '../../src/stores/wsStore';
import { useNotificationStore } from '../../src/stores/notificationStore';
import { useAuthStore } from '../../src/stores/authStore';

// We test the WebSocket hook indirectly via a mock WebSocket class,
// since useWebSocket directly creates a WebSocket connection.

type MockWsInstance = {
  onopen: (() => void) | null;
  onmessage: ((e: { data: string }) => void) | null;
  onclose: ((e: { code: number }) => void) | null;
  onerror: (() => void) | null;
  close: ReturnType<typeof vi.fn>;
  send: ReturnType<typeof vi.fn>;
  url: string;
};

let mockWsInstances: MockWsInstance[] = [];

class MockWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  send = vi.fn();
  url: string;

  constructor(url: string) {
    this.url = url;
    mockWsInstances.push(this as unknown as MockWsInstance);
  }
}

describe('useWebSocket behavior', () => {
  beforeEach(() => {
    mockWsInstances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:8090' });
    useWsStore.setState({ connected: false, lastEvent: null });
    useNotificationStore.setState({ pendingCount: 0, toasts: [] });
    useAuthStore.setState({
      token: 'test-jwt',
      user: null,
      isAuthenticated: true,
      loading: false,
    });
    // Mock getToken to return value
    vi.mock('../../src/api/client', () => ({
      getToken: () => 'test-jwt',
      setToken: vi.fn(),
      clearToken: vi.fn(),
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('connects to correct URL format', async () => {
    const { useWebSocket } = await import('../../src/hooks/useWebSocket');
    renderHook(() => useWebSocket('team1'));

    expect(mockWsInstances.length).toBeGreaterThanOrEqual(1);
    const ws = mockWsInstances[0];
    expect(ws.url).toContain('/api/teams/team1/ws');
    expect(ws.url).toContain('token=test-jwt');
  });

  it('sets connected on open', async () => {
    const { useWebSocket } = await import('../../src/hooks/useWebSocket');
    renderHook(() => useWebSocket('team1'));

    const ws = mockWsInstances[0];
    act(() => { ws.onopen?.(); });

    expect(useWsStore.getState().connected).toBe(true);
  });

  it('calls handler on message', async () => {
    const { useWebSocket } = await import('../../src/hooks/useWebSocket');
    renderHook(() => useWebSocket('team1'));

    const ws = mockWsInstances[0];
    act(() => { ws.onopen?.(); });
    act(() => {
      ws.onmessage?.({ data: JSON.stringify({ type: 'new_question', data: {} }) });
    });

    const lastEvent = useWsStore.getState().lastEvent;
    expect(lastEvent).toBeTruthy();
    expect(lastEvent!.type).toBe('new_question');
  });

  it('increments pending on new_question event', async () => {
    const { useWebSocket } = await import('../../src/hooks/useWebSocket');
    renderHook(() => useWebSocket('team1'));

    const ws = mockWsInstances[0];
    act(() => { ws.onopen?.(); });
    act(() => {
      ws.onmessage?.({ data: JSON.stringify({ type: 'new_question', data: {} }) });
    });

    expect(useNotificationStore.getState().pendingCount).toBe(1);
  });

  it('logs out on 4001 close code', async () => {
    const logoutMock = vi.fn();
    useAuthStore.setState({ logout: logoutMock });

    const { useWebSocket } = await import('../../src/hooks/useWebSocket');
    renderHook(() => useWebSocket('team1'));

    const ws = mockWsInstances[0];
    act(() => { ws.onclose?.({ code: 4001 }); });

    expect(logoutMock).toHaveBeenCalled();
  });
});
