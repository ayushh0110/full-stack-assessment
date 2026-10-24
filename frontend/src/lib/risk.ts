import type { LevelKey, RiskLevel } from '../api/types';

export const RISK_COLORS = {
  low: '#2e9d4a',
  moderate: '#f2c12e',
  high: '#f08c2e',
  severe: '#d6342c',
  noTravel: '#6b1f7a',
  unknown: '#9aa3ad',
} as const;

interface RiskMeta {
  label: string;
  code: string;
  key: LevelKey;
  color: string;
  /** Text colour on top of `color`, chosen for WCAG AA contrast. */
  text: string;
}

const DARK = '#14181f';
const LIGHT = '#ffffff';

export const RISK: Record<RiskLevel, RiskMeta> = {
  0: { label: 'Low', code: 'L', key: 'low', color: RISK_COLORS.low, text: DARK },
  1: { label: 'Moderate', code: 'M', key: 'moderate', color: RISK_COLORS.moderate, text: DARK },
  2: { label: 'High', code: 'H', key: 'high', color: RISK_COLORS.high, text: DARK },
  3: { label: 'Severe', code: 'S', key: 'severe', color: RISK_COLORS.severe, text: LIGHT },
  4: { label: 'No Travel', code: 'NT', key: 'no_travel', color: RISK_COLORS.noTravel, text: LIGHT },
};

export const UNKNOWN = { label: 'No data', code: '?', color: RISK_COLORS.unknown, text: DARK };

export const LEVELS: RiskLevel[] = [0, 1, 2, 3, 4];

export function riskMeta(level: RiskLevel | null) {
  return level === null ? UNKNOWN : RISK[level];
}
