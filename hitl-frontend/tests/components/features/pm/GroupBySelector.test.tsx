import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GroupBySelector } from '../../../../src/components/features/pm/GroupBySelector';

describe('GroupBySelector', () => {
  it('renders all 4 options', () => {
    render(<GroupBySelector value="status" onChange={vi.fn()} />);
    const select = screen.getByRole('combobox');
    const options = select.querySelectorAll('option');
    expect(options.length).toBe(4);
  });

  it('calls onChange with new value', () => {
    const onChange = vi.fn();
    render(<GroupBySelector value="status" onChange={onChange} />);
    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'assignee' } });
    expect(onChange).toHaveBeenCalledWith('assignee');
  });
});
