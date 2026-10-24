import CheckCircle from '@mui/icons-material/CheckCircle';
import {
  Box,
  Card,
  CardActionArea,
  Chip,
  Skeleton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import type { Exclusion, RecommendationStatus, RouteAssessment, RouteOption } from '../api/types';
import { formatDuration, formatMiles, formatTime } from '../lib/format';
import { RiskBar } from './RiskBar';
import { RiskChip } from './RiskChip';

interface Props {
  route: RouteOption;
  assessment?: RouteAssessment;
  loading: boolean;
  selected: boolean;
  onSelect: () => void;
  arrivalTz: string;
  pick?: { status: RecommendationStatus; isPick: boolean };
  exclusion?: Exclusion;
}

function StatusChip({ pick, exclusion }: Pick<Props, 'pick' | 'exclusion'>) {
  if (pick?.isPick && pick.status === 'recommended') {
    return <Chip size="small" color="success" icon={<CheckCircle />} label="Recommended" />;
  }
  if (pick?.isPick && pick.status === 'no_safe_route') {
    return <Chip size="small" color="warning" label="Least risky — not safe" />;
  }
  if (exclusion) {
    return (
      <Tooltip title={exclusion.detail}>
        <Chip
          size="small"
          variant="outlined"
          color={exclusion.reason === 'no_travel' ? 'error' : 'default'}
          label={exclusion.reason === 'no_travel' ? 'No Travel' : 'Incomplete forecast'}
        />
      </Tooltip>
    );
  }
  return null;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" component="div">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600}>
        {value}
      </Typography>
    </Box>
  );
}

export function RouteCard({
  route,
  assessment,
  loading,
  selected,
  onSelect,
  arrivalTz,
  pick,
  exclusion,
}: Props) {
  const summary = assessment?.summary;
  return (
    <Card
      sx={{
        borderColor: selected ? 'primary.main' : 'divider',
        boxShadow: selected ? (t) => `0 0 0 1px ${t.palette.primary.main}` : 'none',
        transition: 'border-color 120ms, box-shadow 120ms',
      }}
    >
      <CardActionArea onClick={onSelect} aria-pressed={selected} sx={{ p: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1.5} mb={1.5}>
          <Box
            sx={{
              width: 28,
              height: 28,
              borderRadius: '50%',
              display: 'grid',
              placeItems: 'center',
              fontWeight: 700,
              fontSize: 14,
              bgcolor: selected ? 'primary.main' : 'grey.200',
              color: selected ? 'primary.contrastText' : 'text.primary',
              flexShrink: 0,
            }}
          >
            {route.id}
          </Box>
          <Box flex={1} minWidth={0}>
            <Typography variant="subtitle2" noWrap>
              Route {route.id}
              {route.via ? ` · via ${route.via}` : ''}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap component="div">
              {formatMiles(route.distance_mi)} · {formatDuration(route.duration_s)}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap component="div">
              Arrives {formatTime(route.arrival_utc, arrivalTz)}
            </Typography>
          </Box>
          <StatusChip pick={pick} exclusion={exclusion} />
        </Stack>

        {summary ? (
          <>
            <RiskBar summary={summary} />
            <Stack direction="row" spacing={2.5} mt={1.5} alignItems="flex-end">
              <Metric label="Severe" value={formatMiles(summary.miles_by_level.severe)} />
              <Metric label="High" value={formatMiles(summary.miles_by_level.high)} />
              <Metric
                label="Risk index"
                value={summary.risk_index === null ? '—' : summary.risk_index.toFixed(2)}
              />
              <Box flex={1} />
              <Box textAlign="right">
                <Typography variant="caption" color="text.secondary" component="div">
                  Worst
                </Typography>
                <RiskChip level={summary.max_level} />
              </Box>
            </Stack>
            {summary.coverage < 1 && (
              <Typography variant="caption" color="warning.main" component="div" mt={1}>
                Forecast available for {Math.round(summary.coverage * 100)}% of this route.
              </Typography>
            )}
          </>
        ) : loading ? (
          <>
            <Skeleton variant="rounded" height={10} />
            <Stack direction="row" spacing={2.5} mt={1.5}>
              <Skeleton width={48} height={36} />
              <Skeleton width={48} height={36} />
              <Skeleton width={56} height={36} />
            </Stack>
          </>
        ) : null}
      </CardActionArea>
    </Card>
  );
}
