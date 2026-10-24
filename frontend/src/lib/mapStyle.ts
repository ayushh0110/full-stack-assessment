import type { ExpressionSpecification } from 'maplibre-gl';
import { RISK_COLORS } from './risk';

/** Colour for a risk level read by `input`; -1 (no data) is grey. */
export function riskColor(input: ExpressionSpecification): ExpressionSpecification {
  return [
    'match',
    input,
    0,
    RISK_COLORS.low,
    1,
    RISK_COLORS.moderate,
    2,
    RISK_COLORS.high,
    3,
    RISK_COLORS.severe,
    4,
    RISK_COLORS.noTravel,
    RISK_COLORS.unknown,
  ];
}

const hourProperty = (hour: number): ExpressionSpecification => ['get', `r${hour}`];

/** Heatmap cell colour at a forecast hour — each cell shows its exact risk class. */
export function cellColor(hour: number): ExpressionSpecification {
  return riskColor(hourProperty(hour));
}

/** Calm cells stay faint so the corridor reads at a glance; risky cells stand out. */
export function cellOpacity(hour: number): ExpressionSpecification {
  return ['match', hourProperty(hour), 0, 0.14, -1, 0.22, 0.55];
}
