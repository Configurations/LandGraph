import { useCallback, useEffect, useRef } from 'react';

function playNotificationSound(): void {
  try {
    const ctx = new AudioContext();
    const now = ctx.currentTime;

    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.frequency.value = 800;
    osc1.type = 'sine';
    gain1.gain.value = 0.15;
    osc1.connect(gain1).connect(ctx.destination);
    osc1.start(now);
    osc1.stop(now + 0.1);

    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.frequency.value = 1000;
    osc2.type = 'sine';
    gain2.gain.value = 0.15;
    osc2.connect(gain2).connect(ctx.destination);
    osc2.start(now + 0.12);
    osc2.stop(now + 0.22);

    setTimeout(() => ctx.close(), 500);
  } catch {
    // Web Audio not available
  }
}

interface UseNotificationsReturn {
  notify: (title: string, body: string) => void;
  permissionGranted: boolean;
}

export function useNotifications(): UseNotificationsReturn {
  const permissionRef = useRef(
    typeof Notification !== 'undefined' ? Notification.permission === 'granted' : false,
  );

  useEffect(() => {
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission().then((result) => {
        permissionRef.current = result === 'granted';
      });
    }
  }, []);

  const notify = useCallback((title: string, body: string) => {
    playNotificationSound();
    if (permissionRef.current && typeof Notification !== 'undefined') {
      new Notification(title, { body, icon: '/favicon.ico' });
    }
  }, []);

  return { notify, permissionGranted: permissionRef.current };
}
