import { useState } from 'react';

const AVATAR_COLORS = [
  'bg-accent-blue',
  'bg-accent-green',
  'bg-accent-orange',
  'bg-accent-purple',
  'bg-accent-yellow',
  'bg-accent-red',
] as const;

type AvatarSize = 'sm' | 'md' | 'lg';

interface AvatarProps {
  name: string;
  imageUrl?: string | null;
  size?: AvatarSize;
  className?: string;
}

const sizeStyles: Record<AvatarSize, string> = {
  sm: 'h-8 w-8 text-xs',
  md: 'h-16 w-16 text-lg',
  lg: 'h-20 w-20 text-xl',
};

function hashName(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export function Avatar({ name, imageUrl, size = 'md', className = '' }: AvatarProps): JSX.Element {
  const [imgError, setImgError] = useState(false);
  const colorIndex = hashName(name) % AVATAR_COLORS.length;
  const bgColor = AVATAR_COLORS[colorIndex];
  const initials = getInitials(name);

  if (imageUrl && !imgError) {
    return (
      <img
        src={imageUrl}
        alt={name}
        title={name}
        onError={() => setImgError(true)}
        className={[
          'inline-flex rounded-full object-cover',
          sizeStyles[size],
          className,
        ].join(' ')}
      />
    );
  }

  return (
    <div
      className={[
        'inline-flex items-center justify-center rounded-full font-semibold text-white',
        bgColor,
        sizeStyles[size],
        className,
      ].join(' ')}
      title={name}
    >
      {initials}
    </div>
  );
}
