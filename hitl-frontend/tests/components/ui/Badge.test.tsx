import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from '../../../src/components/ui/Badge';

describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>Active</Badge>);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('applies blue color by default', () => {
    const { container } = render(<Badge>Info</Badge>);
    const span = container.querySelector('span')!;
    expect(span.className).toContain('bg-accent-blue/15');
    expect(span.className).toContain('text-accent-blue');
  });

  it('applies green color', () => {
    const { container } = render(<Badge color="green">OK</Badge>);
    const span = container.querySelector('span')!;
    expect(span.className).toContain('bg-accent-green/15');
  });

  it('applies red color', () => {
    const { container } = render(<Badge color="red">Error</Badge>);
    const span = container.querySelector('span')!;
    expect(span.className).toContain('bg-accent-red/15');
  });

  it('applies orange color', () => {
    const { container } = render(<Badge color="orange">Warn</Badge>);
    const span = container.querySelector('span')!;
    expect(span.className).toContain('bg-accent-orange/15');
  });

  it('applies purple color', () => {
    const { container } = render(<Badge color="purple">Tag</Badge>);
    const span = container.querySelector('span')!;
    expect(span.className).toContain('bg-accent-purple/15');
  });

  it('shows status dot for status variant', () => {
    const { container } = render(<Badge variant="status" color="green">Live</Badge>);
    const dot = container.querySelector('span span.rounded-full');
    expect(dot).toBeTruthy();
  });

  it('applies count variant centering', () => {
    const { container } = render(<Badge variant="count">5</Badge>);
    const span = container.querySelector('span')!;
    expect(span.className).toContain('justify-center');
  });

  it('applies custom className', () => {
    const { container } = render(<Badge className="ml-2">X</Badge>);
    const span = container.querySelector('span')!;
    expect(span.className).toContain('ml-2');
  });
});
