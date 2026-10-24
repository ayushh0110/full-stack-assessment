import CheckCircle from '@mui/icons-material/CheckCircle';
import { ButtonBase, Typography } from '@mui/material';
import type { RouteOption } from '../api/types';
import { formatDuration, formatMiles } from '../lib/format';

interface Props {
  route: RouteOption;
  selected: boolean;
  recommended: boolean;
  onSelect: () => void;
}

/** Route summary pinned to the map at the route's midpoint. */
export function RouteChip({ route, selected, recommended, onSelect }: Props) {
  return (
    <ButtonBase
      onClick={onSelect}
      aria-label={`Select route ${route.id}`}
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
