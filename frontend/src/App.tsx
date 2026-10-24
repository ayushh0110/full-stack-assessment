import LocalShippingOutlined from '@mui/icons-material/LocalShippingOutlined';
import { Box, Divider, Stack, Typography } from '@mui/material';
import { useCallback, useEffect, useMemo } from 'react';
import { ApiError } from './api/client';
import { useAssessment, useCreateRouteSet, useHeatmap } from './api/hooks';
import type { TripInput } from './api/types';
import { ForecastSlider } from './components/ForecastSlider';
import { Legend } from './components/Legend';
import { MapView } from './components/MapView';
import { ResultsPanel } from './components/ResultsPanel';
import { TripForm } from './components/TripForm';
import { useAppStore } from './store';

const BROWSER_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;
const HOUR_MS = 3_600_000;

export function App() {
  const routeSet = useAppStore((s) => s.routeSet);
  const lastInput = useAppStore((s) => s.lastInput);
  const interval = useAppStore((s) => s.interval);
  const setRouteSet = useAppStore((s) => s.setRouteSet);
  const selectRoute = useAppStore((s) => s.selectRoute);

  const plan = useCreateRouteSet();
  const assessment = useAssessment(routeSet?.id, interval);
  const heatmap = useHeatmap(routeSet?.id);
  const { mutate } = plan;

  const submit = useCallback(
    (input: TripInput) => mutate(input, { onSuccess: (result) => setRouteSet(result, input) }),
    [mutate, setRouteSet],
  );

  // Select the recommended route unless the user has already picked one.
  const recommendedId = assessment.data?.recommendation.route_id ?? null;
  useEffect(() => {
    if (recommendedId && !useAppStore.getState().userSelectedRoute)
      selectRoute(recommendedId, false);
  }, [recommendedId, selectRoute]);

  // Route sets live for an hour on the server; quietly plan again if one has expired.
  const expired = [assessment.error, heatmap.error].some(
    (e) => e instanceof ApiError && e.code === 'route_set_expired',
  );
  useEffect(() => {
    if (expired && lastInput) submit(lastInput);
  }, [expired, lastInput, submit]);

  const forecastStartMs = useMemo(
    () =>
      heatmap.data
        ? Date.parse(heatmap.data.start_utc)
        : Math.floor(Date.now() / HOUR_MS) * HOUR_MS,
    [heatmap.data],
  );
  const planError =
    plan.error instanceof ApiError && Object.keys(plan.error.fields).length
      ? undefined
      : plan.error?.message;
  const fieldErrors = useMemo(
    () => (plan.error instanceof ApiError ? plan.error.fields : {}),
    [plan.error],
  );
  const displayTz = routeSet?.origin_tz ?? BROWSER_TZ;

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        height: '100dvh',
        bgcolor: 'background.default',
      }}
    >
      <Box
        component="aside"
        sx={{
          order: { xs: 2, md: 1 },
          width: { md: 420 },
          flex: { xs: 1, md: 'none' },
          minHeight: 0,
          overflowY: 'auto',
          bgcolor: 'background.paper',
          borderRight: { md: 1 },
          borderTop: { xs: 1, md: 0 },
          borderColor: 'divider',
        }}
      >
        <Box sx={{ px: 3, pt: 3, pb: 2.5 }}>
          <Stack direction="row" spacing={1.25} alignItems="center" mb={0.5}>
            <LocalShippingOutlined color="primary" />
            <Typography variant="h1">Truck Weather Routing</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary">
            Compares three truck routes using the forecast at each checkpoint’s arrival time.
          </Typography>
        </Box>
        <Divider />
        <Box sx={{ p: 3 }}>
          <TripForm onSubmit={submit} submitting={plan.isPending} serverErrors={fieldErrors} />
        </Box>
        {(routeSet || plan.isPending || planError) && (
          <>
            <Divider />
            <Box sx={{ p: 3 }}>
              <ResultsPanel
                routeSet={routeSet}
                planning={plan.isPending}
                planError={planError}
                assessment={assessment.data}
                assessing={assessment.isFetching}
                assessError={expired ? undefined : assessment.error?.message}
                onRetryAssessment={() => assessment.refetch()}
                arrivalTz={lastInput?.destination.tz ?? displayTz}
              />
            </Box>
          </>
        )}
        <Typography variant="caption" color="text.secondary" component="p" sx={{ px: 3, pb: 3 }}>
          Weather: Open-Meteo (NOAA GFS/HRRR). Routing:{' '}
          {routeSet?.truck_aware === false ? 'OSRM (development)' : 'TomTom truck routing'}. Risk
          miles are attributed from checkpoint samples.
        </Typography>
      </Box>

      <Box
        component="main"
        sx={{
          order: { xs: 1, md: 2 },
          position: 'relative',
          flex: { xs: 'none', md: 1 },
          height: { xs: '52dvh', md: 'auto' },
          minWidth: 0,
        }}
      >
        <MapView
          routeSet={routeSet}
          assessment={assessment.data}
          heatmap={heatmap.data}
          recommendedId={recommendedId}
          forecastStartMs={forecastStartMs}
        />
        <Legend />
        <ForecastSlider
          startMs={forecastStartMs}
          tz={displayTz}
          routeSet={routeSet}
          assessment={assessment.data}
          loading={heatmap.isFetching}
          error={heatmap.isError && !expired ? 'Forecast grid unavailable' : undefined}
        />
      </Box>
    </Box>
  );
}
