import FlagOutlined from '@mui/icons-material/FlagOutlined';
import TripOriginOutlined from '@mui/icons-material/TripOriginOutlined';
import {
  Box,
  Button,
  CircularProgress,
  FormHelperText,
  InputAdornment,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import dayjs from 'dayjs';
import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import type { Interval, Place, TripInput } from '../api/types';
import { zoneAbbreviation } from '../lib/format';
import { useAppStore } from '../store';
import { PlaceInput } from './PlaceInput';

const BROWSER_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;
const TARE_LB = 35_000;
const WALL_FORMAT = 'YYYY-MM-DDTHH:mm';

/** The next quarter hour, as wall-clock time in `tz`. */
function nextQuarterHour(tz: string): string {
  const now = dayjs().tz(tz);
  return now
    .add(15 - (now.minute() % 15), 'minute')
    .second(0)
    .format(WALL_FORMAT);
}

interface Props {
  onSubmit: (input: TripInput) => void;
  submitting: boolean;
  serverErrors: Record<string, string>;
}

export function TripForm({ onSubmit, submitting, serverErrors }: Props) {
  const interval = useAppStore((s) => s.interval);
  const setInterval = useAppStore((s) => s.setInterval);
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [load, setLoad] = useState('38000');
  const [departureTouched, setDepartureTouched] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Departure is entered as local time at the origin, so the picker follows the origin's zone.
  const tz = origin?.tz ?? BROWSER_TZ;
  const [departure, setDeparture] = useState(() => nextQuarterHour(tz));
  useEffect(() => {
    if (!departureTouched) setDeparture(nextQuarterHour(tz));
  }, [tz, departureTouched]);

  useEffect(() => setErrors(serverErrors), [serverErrors]);

  const departureValue = dayjs.tz(departure, tz);
  const zoneLabel = `${zoneAbbreviation(tz, departureValue.toDate())}${origin ? '' : ', your time zone'}`;

  function validate(): Record<string, string> {
    const found: Record<string, string> = {};
    if (!origin) found.origin = 'Choose a starting point from the list.';
    if (!destination) found.destination = 'Choose a destination from the list.';
    const lb = Number(load);
    if (load.trim() === '' || !Number.isInteger(lb) || lb < 0 || lb > 80_000) {
      found.load_lb = 'Enter a whole number of pounds from 0 to 80,000.';
    }
    if (!departureValue.isValid()) found.departure_local = 'Enter a departure date and time.';
    return found;
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length || !origin || !destination) return;
    onSubmit({ origin, destination, departure_local: departure, load_lb: Number(load) });
  }

  const loadLb = Number(load);
  const gross = Number.isFinite(loadLb) ? loadLb + TARE_LB : null;

  return (
    <Box component="form" noValidate onSubmit={submit}>
      <Stack spacing={2}>
        <PlaceInput
          label="Origin"
          icon={<TripOriginOutlined fontSize="small" color="action" />}
          value={origin}
          onChange={setOrigin}
          error={errors.origin}
        />
        <PlaceInput
          label="Destination"
          icon={<FlagOutlined fontSize="small" color="action" />}
          value={destination}
          onChange={setDestination}
          error={errors.destination}
        />
        <DateTimePicker
          label={`Departure (${zoneLabel})`}
          value={departureValue}
          timezone={tz}
          onChange={(value) => {
            if (value?.isValid()) {
              setDeparture(value.tz(tz).format(WALL_FORMAT));
              setDepartureTouched(true);
            }
          }}
          minDateTime={dayjs().tz(tz).subtract(1, 'hour')}
          maxDateTime={dayjs().tz(tz).add(7, 'day')}
          slotProps={{
            textField: {
              size: 'small',
              fullWidth: true,
              error: Boolean(errors.departure_local),
              helperText: errors.departure_local ?? 'Local time at the origin',
            },
          }}
        />
        <TextField
          label="Load weight"
          value={load}
          onChange={(event) => setLoad(event.target.value.replace(/[^\d]/g, ''))}
          error={Boolean(errors.load_lb)}
          helperText={
            errors.load_lb ??
            (gross !== null
              ? `Routing assumes gross weight ${gross.toLocaleString('en-US')} lb (load + ${TARE_LB.toLocaleString('en-US')} lb tare)`
              : ' ')
          }
          slotProps={{
            htmlInput: { inputMode: 'numeric' },
            input: { endAdornment: <InputAdornment position="end">lb</InputAdornment> },
          }}
        />
        <Box>
          <Typography variant="caption" color="text.secondary" component="div" mb={0.5}>
            Weather checkpoint every
          </Typography>
          <ToggleButtonGroup
            exclusive
            fullWidth
            size="small"
            color="primary"
            value={interval}
            onChange={(_, value: Interval | null) => value && setInterval(value)}
            aria-label="Checkpoint interval"
          >
            {[10, 25, 50].map((miles) => (
              <ToggleButton key={miles} value={miles}>
                {miles} mi
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          <FormHelperText>Changing this re-checks the weather without re-routing.</FormHelperText>
        </Box>
        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={submitting}
          startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : undefined}
        >
          {submitting ? 'Finding routes…' : 'Plan routes'}
        </Button>
      </Stack>
    </Box>
  );
}
