import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../../ui/Modal';
import { Button } from '../../ui/Button';
import { Input } from '../../ui/Input';
import { Select } from '../../ui/Select';
import { ApiError } from '../../../api/client';

interface InviteMemberModalProps {
  open: boolean;
  onClose: () => void;
  onInvite: (email: string, displayName: string, role: string) => Promise<void>;
  teamId: string;
  className?: string;
}

const ROLE_OPTIONS = [
  { value: 'member', label: 'Member' },
  { value: 'admin', label: 'Admin' },
];

export function InviteMemberModal({
  open,
  onClose,
  onInvite,
  className = '',
}: InviteMemberModalProps): JSX.Element {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState('member');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await onInvite(email, displayName || email.split('@')[0], role);
      setEmail('');
      setDisplayName('');
      setRole('member');
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(t('common.error'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="team.invite"
      className={className}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button loading={loading} onClick={() => {
            const form = document.getElementById('invite-form') as HTMLFormElement | null;
            form?.requestSubmit();
          }}>
            {t('team.invite')}
          </Button>
        </>
      }
    >
      <form id="invite-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label={t('team.invite_email')}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          label={t('auth.email')}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder={email.split('@')[0] || ''}
        />
        <Select
          label={t('team.invite_role')}
          value={role}
          onChange={(e) => setRole(e.target.value)}
          options={ROLE_OPTIONS}
        />
        {error && <p className="text-sm text-accent-red">{error}</p>}
      </form>
    </Modal>
  );
}
