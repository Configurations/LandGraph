import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PulseMetricCards } from '../../../../src/components/features/pm/PulseMetricCards';
import type { MetricValue } from '../../../../src/api/types';

const velocity: MetricValue = { value: 12, label: 'last 7 days', unit: 'issues' };
const throughput: MetricValue = { value: 3.5, label: 'per week (30d avg)', unit: 'issues/wk' };
const cycleTime: MetricValue = { value: 48, label: 'avg (30d)', unit: 'hours' };
const burndownTotal: MetricValue = { value: 25, label: 'remaining', unit: 'points' };

describe('PulseMetricCards', () => {
  it('renders 4 metric cards', () => {
    const { container } = render(
      <PulseMetricCards
        velocity={velocity}
        throughput={throughput}
        cycleTime={cycleTime}
        burndownTotal={burndownTotal}
      />,
    );
    // Grid with 4 Card children
    const cards = container.querySelectorAll('.rounded-xl');
    expect(cards.length).toBe(4);
  });

  it('displays values in each card', () => {
    render(
      <PulseMetricCards
        velocity={velocity}
        throughput={throughput}
        cycleTime={cycleTime}
        burndownTotal={burndownTotal}
      />,
    );
    expect(screen.getByText('12')).toBeTruthy();
    expect(screen.getByText('3.5')).toBeTruthy();
    expect(screen.getByText('48')).toBeTruthy();
    expect(screen.getByText('25')).toBeTruthy();
  });

  it('shows label keys for each metric', () => {
    render(
      <PulseMetricCards
        velocity={velocity}
        throughput={throughput}
        cycleTime={cycleTime}
        burndownTotal={burndownTotal}
      />,
    );
    expect(screen.getByText('pulse.velocity')).toBeTruthy();
    expect(screen.getByText('pulse.throughput')).toBeTruthy();
    expect(screen.getByText('pulse.cycle_time')).toBeTruthy();
    expect(screen.getByText('pulse.burndown')).toBeTruthy();
  });

  it('shows subtitles (label text)', () => {
    render(
      <PulseMetricCards
        velocity={velocity}
        throughput={throughput}
        cycleTime={cycleTime}
        burndownTotal={burndownTotal}
      />,
    );
    expect(screen.getByText('last 7 days')).toBeTruthy();
    expect(screen.getByText('per week (30d avg)')).toBeTruthy();
  });
});
