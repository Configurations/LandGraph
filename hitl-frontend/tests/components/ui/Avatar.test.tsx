import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Avatar } from '../../../src/components/ui/Avatar';

describe('Avatar', () => {
  it('shows initials when no imageUrl', () => {
    render(<Avatar name="Lead Dev" />);
    expect(screen.getByText('LD')).toBeInTheDocument();
  });

  it('shows image when imageUrl provided', () => {
    const { container } = render(
      <Avatar name="Lead Dev" imageUrl="/avatars/test/lead.png" />,
    );
    const img = container.querySelector('img');
    expect(img).toBeTruthy();
    expect(img?.getAttribute('src')).toBe('/avatars/test/lead.png');
  });

  it('falls back to initials when imageUrl is null', () => {
    render(<Avatar name="Lead Dev" imageUrl={null} />);
    expect(screen.getByText('LD')).toBeInTheDocument();
  });

  it('falls back to initials on image error', () => {
    const { container } = render(
      <Avatar name="Lead Dev" imageUrl="/avatars/broken.png" />,
    );
    const img = container.querySelector('img');
    expect(img).toBeTruthy();
    // Simulate error
    fireEvent.error(img!);
    // After error, should show initials
    expect(screen.getByText('LD')).toBeInTheDocument();
  });

  it('respects size prop', () => {
    const { container } = render(<Avatar name="Test" size="lg" />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('h-10');
    expect(el.className).toContain('w-10');
  });
});
