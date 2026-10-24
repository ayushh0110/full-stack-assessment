import Close from '@mui/icons-material/Close';
import { Box, Divider, IconButton, Stack, Typography } from '@mui/material';
import type { Checkpoint, RiskLevel } from '../api/types';
import { formatTime } from '../lib/format';
import { RiskChip } from './RiskChip';

interface Props {
  checkpoint: Checkpoint;
  routeId: string;
  originTz: string;
  onClose: () => void;
}

function Row({ label, value, level }: { label: string; value: string; level: RiskLevel | null }) {
  return (
    <Stack direction="row" alignItems="center" spacing={1} py={0.25}>
      <Typography variant="body2" color="text.secondary" width={44}>
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600} flex={1}>
        {value}
      </Typography>
      {level !== null && <RiskChip level={level} />}
    </Stack>
  );
}

export function CheckpointCard({ checkpoint: cp, routeId, originTz, onClose }: Props) {
  const unknown = cp.level === null;
  const localDiffers = cp.tz !== originTz;
  return (
    <Box sx={{ p: 1.75, width: 272 }}>
      <Stack direction="row" alignItems="flex-start" spacing={1}>
        <Box flex={1}>
          <Typography variant="overline" color="text.secondary" component="div">
            Route {routeId} · mile {Math.round(cp.mile).toLocaleString('en-US')}
          </Typography>
          <Typography variant="subtitle2">ETA {formatTime(cp.eta_utc, originTz)}</Typography>
          {localDiffers && (
            <Typography variant="caption" color="text.secondary">
              {formatTime(cp.eta_utc, cp.tz)} local
            </Typography>
          )}
        </Box>
        <RiskChip level={cp.level} />
        <IconButton size="small" aria-label="Close" onClick={onClose} sx={{ mt: -0.5, mr: -0.75 }}>
          <Close fontSize="small" />
        </IconButton>
      </Stack>
      <Divider sx={{ my: 1.25 }} />
      {unknown ? (
        <Typography variant="body2" color="text.secondary">
          No forecast is available for this checkpoint, so it isn&apos;t counted as safe.
        </Typography>
      ) : (
        <>
          <Row label="Wind" value={`${cp.wind_mph?.toFixed(0)} mph`} level={cp.levels.wind} />
          <Row label="Rain" value={`${cp.rain_in_hr?.toFixed(2)} in/hr`} level={cp.levels.rain} />
          <Row label="Snow" value={`${cp.snow_in_hr?.toFixed(2)} in/hr`} level={cp.levels.snow} />
          <Box component="ul" sx={{ m: 0, mt: 1, pl: 2 }}>
            {cp.reasons.map((reason) => (
              <Typography component="li" variant="caption" key={reason}>
                {reason}
              </Typography>
            ))}
          </Box>
        </>
      )}
      <Typography variant="caption" color="text.secondary" component="div" mt={1}>
        Covers miles {Math.round(cp.from_mi)}–{Math.round(cp.to_mi)} of the route
      </Typography>
    </Box>
  );
}
