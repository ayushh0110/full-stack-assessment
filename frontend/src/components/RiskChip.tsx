import { Chip } from '@mui/material';
import type { RiskLevel } from '../api/types';
import { riskMeta } from '../lib/risk';

export function RiskChip({
  level,
  size = 'small',
}: {
  level: RiskLevel | null;
  size?: 'small' | 'medium';
}) {
  const meta = riskMeta(level);
  return (
    <Chip
      size={size}
      label={meta.label}
      sx={{
        bgcolor: meta.color,
        color: meta.text,
        fontWeight: 600,
        height: size === 'small' ? 22 : undefined,
      }}
    />
  );
}
