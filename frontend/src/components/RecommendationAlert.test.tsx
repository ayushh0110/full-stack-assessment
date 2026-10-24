import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Recommendation } from '../api/types';
import { RecommendationAlert } from './RecommendationAlert';

const base: Recommendation = {
  status: 'recommended',
  route_id: 'B',
  explanation: 'Route B is recommended: it has the fewest Severe miles.',
  excluded: [
    { route_id: 'C', reason: 'no_travel', detail: 'Route C: No Travel conditions at mile 412.' },
  ],
  comparison: [],
};

describe('RecommendationAlert', () => {
  it('shows the pick, the reason and the exclusions', () => {
    render(<RecommendationAlert recommendation={base} />);
    expect(screen.getByText('Route B recommended')).toBeInTheDocument();
    expect(screen.getByText(/fewest Severe miles/)).toBeInTheDocument();
    expect(screen.getByText(/mile 412/)).toBeInTheDocument();
  });

  it('warns when no route is safe', () => {
    render(<RecommendationAlert recommendation={{ ...base, status: 'no_safe_route' }} />);
    expect(screen.getByText('No safe route at this departure time')).toBeInTheDocument();
  });

  it('offers a retry when forecasts are missing', () => {
    const onRetry = vi.fn();
    render(
      <RecommendationAlert
        recommendation={{ ...base, status: 'insufficient_data', route_id: null }}
        onRetry={onRetry}
      />,
    );
    screen.getByRole('button', { name: 'Retry' }).click();
    expect(onRetry).toHaveBeenCalled();
  });
});
