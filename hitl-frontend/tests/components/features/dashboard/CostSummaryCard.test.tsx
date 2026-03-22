import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CostSummaryCard } from '../../../../src/components/features/dashboard/CostSummaryCard';
import type { CostSummary } from '../../../../src/api/types';

function makeCost(overrides: Partial<CostSummary> = {}): CostSummary {
  return {
    project_slug: 'demo', team_id: 'team1',
    phase: 'Discovery', agent_id: 'analyst',
    total_cost_usd: 0.50, task_count: 2, avg_cost_per_task: 0.25,
    ...overrides,
  };
}

describe('CostSummaryCard', () => {
  it('shows total cost', () => {
    const costs = [makeCost({ total_cost_usd: 1.25 }), makeCost({ total_cost_usd: 0.75, phase: 'Build' })];
    render(<CostSummaryCard costs={costs} budget={10} />);
    expect(screen.getByText('$2.00')).toBeInTheDocument();
  });

  it('shows phase breakdown', () => {
    const costs = [
      makeCost({ phase: 'Discovery', total_cost_usd: 1.0 }),
      makeCost({ phase: 'Build', total_cost_usd: 2.0 }),
    ];
    render(<CostSummaryCard costs={costs} budget={10} />);
    expect(screen.getByText('Discovery')).toBeInTheDocument();
    expect(screen.getByText('Build')).toBeInTheDocument();
    expect(screen.getByText('$2.00')).toBeInTheDocument();
    expect(screen.getByText('$1.00')).toBeInTheDocument();
  });

  it('shows budget warning when over', () => {
    const costs = [makeCost({ total_cost_usd: 15 })];
    render(<CostSummaryCard costs={costs} budget={10} />);
    expect(screen.getByText('dashboard.over_budget')).toBeInTheDocument();
  });

  it('does not show budget warning when under', () => {
    const costs = [makeCost({ total_cost_usd: 5 })];
    render(<CostSummaryCard costs={costs} budget={10} />);
    expect(screen.queryByText('dashboard.over_budget')).not.toBeInTheDocument();
  });
});
