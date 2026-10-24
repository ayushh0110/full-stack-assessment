import { Alert, AlertTitle, Box, Button } from '@mui/material';
import type { Recommendation } from '../api/types';

interface Props {
  recommendation: Recommendation;
  onRetry?: () => void;
}

export function RecommendationAlert({ recommendation, onRetry }: Props) {
  const { status, route_id, explanation, excluded } = recommendation;
  const details = excluded.length > 0 && (
    <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5 }}>
      {excluded.map((e) => (
        <li key={e.route_id}>{e.detail}</li>
      ))}
    </Box>
  );

  if (status === 'recommended') {
    return (
      <Alert severity="success" variant="outlined">
        <AlertTitle>Route {route_id} recommended</AlertTitle>
        {explanation}
        {details}
      </Alert>
    );
  }
  if (status === 'no_safe_route') {
    return (
      <Alert severity="warning">
        <AlertTitle>No safe route at this departure time</AlertTitle>
        {explanation}
        {details}
      </Alert>
    );
  }
  return (
    <Alert
      severity="error"
      action={
        onRetry && (
          <Button color="inherit" size="small" onClick={onRetry}>
            Retry
          </Button>
        )
      }
    >
      <AlertTitle>Not enough forecast data</AlertTitle>
      {explanation}
      {details}
    </Alert>
  );
}
