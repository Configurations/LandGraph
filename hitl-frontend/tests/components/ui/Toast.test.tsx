import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { ToastContainer } from '../../../src/components/ui/Toast';
import { useNotificationStore } from '../../../src/stores/notificationStore';

describe('ToastContainer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Reset store state
    useNotificationStore.setState({ toasts: [], pendingCount: 0 });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders toast with correct role', () => {
    act(() => {
      useNotificationStore.getState().addToast('success', 'toast.saved');
    });

    render(<ToastContainer />);
    const alerts = screen.getAllByRole('alert');
    expect(alerts.length).toBe(1);
  });

  it('renders success toast styling', () => {
    act(() => {
      useNotificationStore.getState().addToast('success', 'toast.ok');
    });

    const { container } = render(<ToastContainer />);
    const toast = container.querySelector('[role="alert"]')!;
    expect(toast.className).toContain('border-accent-green');
  });

  it('renders error toast styling', () => {
    act(() => {
      useNotificationStore.getState().addToast('error', 'toast.fail');
    });

    const { container } = render(<ToastContainer />);
    const toast = container.querySelector('[role="alert"]')!;
    expect(toast.className).toContain('border-accent-red');
  });

  it('auto-dismisses after timeout', () => {
    act(() => {
      useNotificationStore.getState().addToast('info', 'toast.temp');
    });

    render(<ToastContainer />);
    expect(screen.getAllByRole('alert').length).toBe(1);

    // Advance past the 4000ms auto-dismiss
    act(() => {
      vi.advanceTimersByTime(4500);
    });

    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders multiple toasts', () => {
    act(() => {
      const store = useNotificationStore.getState();
      store.addToast('success', 'toast.one');
      store.addToast('error', 'toast.two');
    });

    render(<ToastContainer />);
    expect(screen.getAllByRole('alert').length).toBe(2);
  });
});
