import HourglassTop from '@mui/icons-material/HourglassTop';
import { Alert, Box, Button, LinearProgress, Skeleton, Stack, Typography } from '@mui/material';
import { useWeatherRetryIn } from '../api/hooks';
import type { Assessment, RouteSet } from '../api/types';
import { formatLoad } from '../lib/format';
import { useAppStore } from '../store';
import { RecommendationAlert } from './RecommendationAlert';
import { RouteCard } from './RouteCard';
import { WhyThisRoute } from './WhyThisRoute';

interface Props {
  routeSet: RouteSet | null;
  planning: boolean;
  planError?: string;
  assessment?: Assessment;
  assessing: boolean;
  assessError?: string;
  onRetryAssessment: () => void;
  arrivalTz: string;
}

export function ResultsPanel({
  routeSet,
  planning,
  planError,
  assessment,
  assessing,
  assessError,
  onRetryAssessment,
  arrivalTz,
}: Props) {
  const selectedRouteId = useAppStore((s) => s.selectedRouteId);
  const selectRoute = useAppStore((s) => s.selectRoute);
  const interval = useAppStore((s) => s.interval);
  const retryIn = useWeatherRetryIn();

  if (planError) {
    return <Alert severity="error">{planError}</Alert>;
  }
  if (!routeSet) {
    return planning ? (
      <Stack spacing={1.5}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} variant="rounded" height={104} />
        ))}
      </Stack>
    ) : null;
  }

  const recommendation = assessment?.recommendation;
  const byId = new Map(assessment?.routes.map((r) => [r.id, r]));
  const excluded = new Map(recommendation?.excluded.map((e) => [e.route_id, e]));

  return (
    <Stack spacing={1.5}>
      <Box>
        <Typography variant="subtitle2" component="h2">
          {routeSet.routes.length} route{routeSet.routes.length === 1 ? '' : 's'}
          <Typography component="span" variant="body2" color="text.secondary">
            {' '}
            · {formatLoad(routeSet.load_lb)} load · checkpoints every {interval} mi
          </Typography>
        </Typography>
        <Box sx={{ height: 4, mt: 1 }}>
          {(assessing || planning) && <LinearProgress sx={{ borderRadius: 2 }} />}
        </Box>
        {assessing && !assessment && (
          <Typography variant="caption" color="text.secondary">
            Checking the forecast at each checkpoint’s ETA…
          </Typography>
        )}
      </Box>

      {retryIn > 0 && (
        <Alert severity="info" variant="outlined" icon={<HourglassTop fontSize="inherit" />}>
          Weather service rate limit reached. Retrying in {retryIn} s…
        </Alert>
      )}

      {assessError && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={onRetryAssessment}>
              Retry
            </Button>
          }
        >
          {assessError}
        </Alert>
      )}
      {recommendation && (
        <RecommendationAlert recommendation={recommendation} onRetry={onRetryAssessment} />
      )}

      {routeSet.routes.map((route) => (
        <RouteCard
          key={route.id}
          route={route}
          assessment={byId.get(route.id)}
          loading={assessing}
          selected={route.id === selectedRouteId}
          onSelect={() => selectRoute(route.id)}
          arrivalTz={arrivalTz}
          pick={
            recommendation && {
              status: recommendation.status,
              isPick: recommendation.route_id === route.id,
            }
          }
          exclusion={excluded.get(route.id)}
        />
      ))}

      {recommendation && (
        <WhyThisRoute recommendation={recommendation} routeIds={routeSet.routes.map((r) => r.id)} />
      )}

      {routeSet.notes.map((note) => (
        <Alert key={note} severity={routeSet.truck_aware ? 'info' : 'warning'} variant="outlined">
          {note}
        </Alert>
      ))}
    </Stack>
  );
}
