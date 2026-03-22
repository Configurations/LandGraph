import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '../../../src/components/ui/Button';

describe('Button', () => {
  it('renders with text', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
  });

  it('renders primary variant by default', () => {
    render(<Button>Primary</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('bg-accent-blue');
  });

  it('renders secondary variant', () => {
    render(<Button variant="secondary">Sec</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('bg-surface-tertiary');
  });

  it('renders danger variant', () => {
    render(<Button variant="danger">Del</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('bg-accent-red');
  });

  it('renders ghost variant', () => {
    render(<Button variant="ghost">Ghost</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('bg-transparent');
  });

  it('shows spinner when loading', () => {
    render(<Button loading>Save</Button>);
    const btn = screen.getByRole('button');
    // Button should be disabled when loading
    expect(btn).toBeDisabled();
    // Spinner SVG has animate-spin class
    const svg = btn.querySelector('svg.animate-spin');
    expect(svg).toBeTruthy();
  });

  it('disabled state prevents clicks', () => {
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>No</Button>);
    const btn = screen.getByRole('button');
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
    expect(btn).toBeDisabled();
  });

  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('applies custom className', () => {
    render(<Button className="mt-4">X</Button>);
    expect(screen.getByRole('button').className).toContain('mt-4');
  });
});
