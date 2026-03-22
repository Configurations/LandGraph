import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getGoogleClientId } from '../../../api/auth';
import { useAuthStore } from '../../../stores/authStore';
import { Button } from '../../ui/Button';

interface GoogleSignInProps {
  className?: string;
}

interface GoogleCredentialResponse {
  credential: string;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: GoogleCredentialResponse) => void;
          }) => void;
          renderButton: (
            element: HTMLElement,
            config: { theme: string; size: string; width: number },
          ) => void;
        };
      };
    };
  }
}

export function GoogleSignIn({ className = '' }: GoogleSignInProps): JSX.Element | null {
  const { t } = useTranslation();
  const loginWithGoogle = useAuthStore((s) => s.loginWithGoogle);
  const [clientId, setClientId] = useState<string | null>(null);
  const [scriptLoaded, setScriptLoaded] = useState(false);
  const [error, setError] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getGoogleClientId()
      .then((res) => {
        if (res.enabled && res.client_id) {
          setClientId(res.client_id);
        }
      })
      .catch(() => {
        // Google not configured, hide button
      });
  }, []);

  useEffect(() => {
    if (!clientId) return;
    if (document.getElementById('google-gsi-script')) {
      setScriptLoaded(true);
      return;
    }
    const script = document.createElement('script');
    script.id = 'google-gsi-script';
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = () => setScriptLoaded(true);
    document.head.appendChild(script);
  }, [clientId]);

  useEffect(() => {
    if (!scriptLoaded || !clientId || !containerRef.current || !window.google) return;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (response) => {
        loginWithGoogle(response.credential).catch(() => {
          setError(t('auth.invalid_credentials'));
        });
      },
    });
    window.google.accounts.id.renderButton(containerRef.current, {
      theme: 'filled_black',
      size: 'large',
      width: 320,
    });
  }, [scriptLoaded, clientId, loginWithGoogle, t]);

  if (!clientId) return null;

  return (
    <div className={`flex flex-col items-center gap-2 ${className}`}>
      <div className="flex items-center gap-3 w-full">
        <div className="flex-1 h-px bg-border" />
        <span className="text-xs text-content-quaternary">{t('auth.sign_in_google')}</span>
        <div className="flex-1 h-px bg-border" />
      </div>
      <div ref={containerRef} />
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
