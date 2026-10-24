import CheckCircle from '@mui/icons-material/CheckCircle';
import { Box, ButtonBase, Typography } from '@mui/material';
import type { RiskLevel, RouteOption } from '../api/types';
import { formatDuration, formatMiles } from '../lib/format';
import { riskMeta } from '../lib/risk';

interface Props {
  route: RouteOption;
  selected: boolean;
  recommended: boolean;
  /** Worst risk level on the route, once assessed (null: no forecast). */
  worst?: RiskLevel | null;
  onSelect: () => void;
}

/** Route summary pinned to the map at the route's midpoint. */
export function RouteChip({ route, selected, recommended, worst, onSelect }: Props) {
  const risk = worst === undefined ? null : riskMeta(worst);
  return (
    <ButtonBase
      onClick={onSelect}
      aria-label={`Select route ${route.id}${risk ? `, worst risk ${risk.label}` : ''}`}
      title={risk ? `Worst risk on route ${route.id}: ${risk.label}` : undefined}
      sx={{
        px: 1,
        py: 0.5,
        gap: 0.75,
        borderRadius: 999,
        border: 1,
        borderColor: selected ? 'primary.main' : 'divider',
        bgcolor: selected ? 'primary.main' : 'background.paper',
        color: selected ? 'primary.contrastText' : 'text.primary',
        boxShadow: '0 1px 4px rgba(20, 24, 31, 0.18)',
        whiteSpace: 'nowrap',
      }}
    >
      {risk && (
        <Box
          sx={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            bgcolor: risk.color,
            border: '1.5px solid #fff',
            boxShadow: '0 0 0 1px rgba(20,24,31,.45)',
          }}
        />
      )}
      <Typography variant="caption" fontWeight={700}>
        {route.id}
      </Typography>
      <Typography variant="caption">
        {formatMiles(route.distance_mi)} · {formatDuration(route.duration_s)}
      </Typography>
      {recommended && (
        <CheckCircle sx={{ fontSize: 15, color: selected ? 'inherit' : 'success.main' }} />
      )}
    </ButtonBase>
  );
}
