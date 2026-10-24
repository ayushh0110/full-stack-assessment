import { Box, Tooltip } from '@mui/material';
import type { RouteSummary } from '../api/types';
import { formatMiles } from '../lib/format';
import { LEVELS, RISK, UNKNOWN } from '../lib/risk';

/** Stacked bar of attributed miles per risk level (plus miles without a forecast). */
export function RiskBar({ summary }: { summary: RouteSummary }) {
  const parts = [
    ...LEVELS.map((level) => ({
      key: RISK[level].key,
      label: RISK[level].label,
      color: RISK[level].color,
      miles: summary.miles_by_level[RISK[level].key],
    })),
    { key: 'unknown', label: UNKNOWN.label, color: UNKNOWN.color, miles: summary.unknown_mi },
  ].filter((part) => part.miles > 0);
  const total = parts.reduce((sum, part) => sum + part.miles, 0) || 1;

  return (
    <Box
      role="img"
      aria-label={parts.map((p) => `${p.label} ${formatMiles(p.miles)}`).join(', ')}
      sx={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', bgcolor: 'divider' }}
    >
      {parts.map((part) => (
        <Tooltip key={part.key} title={`${part.label}: ${formatMiles(part.miles)}`}>
          <Box sx={{ width: `${(part.miles / total) * 100}%`, bgcolor: part.color, minWidth: 3 }} />
        </Tooltip>
      ))}
    </Box>
  );
}
