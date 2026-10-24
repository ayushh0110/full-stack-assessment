import Pause from '@mui/icons-material/Pause';
import PlayArrow from '@mui/icons-material/PlayArrow';
import { Box, IconButton, LinearProgress, Paper, Slider, Stack, Typography } from '@mui/material';
import { useEffect } from 'react';
import type { Assessment, RouteSet } from '../api/types';
import { formatTime } from '../lib/format';
import { useAppStore } from '../store';

const HOURS = 48;
const STEP_MS = 700;
const MARKS = [0, 12, 24, 36, 48].map((value) => ({
  value,
  label: value === 0 ? 'Now' : `+${value} h`,
}));

interface Props {
  startMs: number;
  tz: string;
  routeSet: RouteSet | null;
  assessment?: Assessment;
  loading: boolean;
  error?: string;
}

/** Where the selected route puts the truck at the slider time, in words. */
function truckStatus(
  timeMs: number,
  routeSet: RouteSet,
  routeId: string | null,
  assessment?: Assessment,
) {
  const route = routeSet.routes.find((r) => r.id === routeId);
  if (!route) return '';
  const departure = Date.parse(routeSet.departure_utc);
  const arrival = Date.parse(route.arrival_utc);
  if (timeMs < departure)
    return `Route ${route.id}: truck departs ${formatTime(departure, routeSet.origin_tz)}`;
  if (timeMs > arrival) return `Route ${route.id}: truck has arrived`;
  const checkpoints = assessment?.routes.find((r) => r.id === route.id)?.checkpoints ?? [];
  let mile = (route.distance_mi * (timeMs - departure)) / (arrival - departure);
  for (let i = 1; i < checkpoints.length; i++) {
    const [a, b] = [checkpoints[i - 1], checkpoints[i]];
    const [ta, tb] = [Date.parse(a.eta_utc), Date.parse(b.eta_utc)];
    if (timeMs <= tb) {
      mile = a.mile + ((b.mile - a.mile) * (timeMs - ta)) / Math.max(1, tb - ta);
      break;
    }
  }
  return `Route ${route.id}: truck near mile ${Math.round(mile).toLocaleString('en-US')}`;
}

export function ForecastSlider({ startMs, tz, routeSet, assessment, loading, error }: Props) {
  const hour = useAppStore((s) => s.hour);
  const setHour = useAppStore((s) => s.setHour);
  const playing = useAppStore((s) => s.playing);
  const setPlaying = useAppStore((s) => s.setPlaying);
  const selectedRouteId = useAppStore((s) => s.selectedRouteId);

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      const next = useAppStore.getState().hour + 1;
      if (next > HOURS) setPlaying(false);
      else setHour(next);
    }, STEP_MS);
    return () => clearInterval(timer);
  }, [playing, setHour, setPlaying]);

  const timeMs = startMs + hour * 3_600_000;
  const disabled = !routeSet || loading || Boolean(error);
  const status = error
    ? error
    : loading
      ? 'Loading the forecast grid…'
      : routeSet
        ? truckStatus(timeMs, routeSet, selectedRouteId, assessment)
        : 'Plan a trip to see the weather along it';

  return (
    <Paper
      elevation={0}
      sx={{
        position: 'absolute',
        left: { xs: 8, sm: 16 },
        right: { xs: 8, sm: 16 },
        bottom: { xs: 28, sm: 32 },
        mx: 'auto',
        maxWidth: 720,
        px: 2,
        pt: 1.25,
        pb: 0.5,
        border: 1,
        borderColor: 'divider',
        bgcolor: 'rgba(255,255,255,0.96)',
        overflow: 'hidden',
      }}
    >
      {loading && (
        <LinearProgress sx={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2 }} />
      )}
      <Stack direction="row" alignItems="center" spacing={1.5}>
        <IconButton
          aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}
          onClick={() => {
            if (!playing && hour >= HOURS) setHour(0);
            setPlaying(!playing);
          }}
          disabled={disabled}
          color="primary"
          sx={{ bgcolor: 'action.hover' }}
        >
          {playing ? <Pause /> : <PlayArrow />}
        </IconButton>
        <Box flex={1} minWidth={0}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            justifyContent="space-between"
            alignItems={{ xs: 'flex-start', sm: 'baseline' }}
            columnGap={1}
            minWidth={0}
          >
            <Typography variant="subtitle2" noWrap maxWidth="100%">
              Forecast · {formatTime(timeMs, tz)}
            </Typography>
            <Typography
              variant="caption"
              color={error ? 'error' : 'text.secondary'}
              noWrap
              maxWidth="100%"
            >
              {status}
            </Typography>
          </Stack>
          <Slider
            value={hour}
            min={0}
            max={HOURS}
            step={1}
            marks={MARKS}
            onChange={(_, value) => {
              setPlaying(false);
              setHour(value as number);
            }}
            disabled={disabled}
            valueLabelDisplay="auto"
            valueLabelFormat={(value) => (value === 0 ? 'Now' : `+${value} h`)}
            aria-label="Forecast hour"
            getAriaValueText={(value) => formatTime(startMs + value * 3_600_000, tz)}
            size="small"
            sx={{ mt: 0.25, '& .MuiSlider-markLabel': { fontSize: 11 } }}
          />
        </Box>
      </Stack>
    </Paper>
  );
}
