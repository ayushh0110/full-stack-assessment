import ExpandMore from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { Recommendation } from '../api/types';
import { formatCriterion } from '../lib/format';

const ELIGIBILITY = new Set(['no_travel_mi', 'coverage']);

/** The ranking rules as a table: eligibility first, then the brief's order, deciding row marked. */
export function WhyThisRoute({
  recommendation,
  routeIds,
}: {
  recommendation: Recommendation;
  routeIds: string[];
}) {
  const pick = recommendation.route_id;
  return (
    <Accordion
      disableGutters
      variant="outlined"
      sx={{ borderRadius: 2.5, '&:before': { display: 'none' } }}
    >
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Typography variant="subtitle2">Why this route?</Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        <Typography variant="caption" color="text.secondary" component="p" mb={1}>
          Routes with No Travel conditions or missing forecasts are ruled out first. The rest are
          ranked in order: fewest Severe miles, fewest High miles, lowest risk index (average level,
          0 Low – 4 No Travel), then shortest travel time.
        </Typography>
        {/* Tight, even cell padding keeps three route columns inside a phone-width card; the
            wrapper scrolls rather than overflowing if a narrow screen still can't fit them. */}
        <Box sx={{ overflowX: 'auto', mx: -1 }}>
          <Table
            size="small"
            aria-label="Route comparison"
            sx={{ '& .MuiTableCell-root': { px: 0.75 } }}
          >
            <TableHead>
              <TableRow>
                <TableCell>Criterion</TableCell>
                {routeIds.map((id) => (
                  <TableCell key={id} align="right" sx={{ fontWeight: id === pick ? 700 : 500 }}>
                    {id}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {recommendation.comparison.map((row) => (
                <TableRow
                  key={row.criterion}
                  sx={row.decisive ? { bgcolor: 'rgba(36, 83, 199, 0.08)' } : undefined}
                >
                  <TableCell>
                    <Typography variant="body2" fontWeight={row.decisive ? 700 : 400}>
                      {row.label}
                    </Typography>
                    {(row.decisive || ELIGIBILITY.has(row.criterion)) && (
                      <Typography
                        variant="caption"
                        color={row.decisive ? 'primary' : 'text.secondary'}
                      >
                        {row.decisive ? 'Deciding factor' : 'Eligibility'}
                      </Typography>
                    )}
                  </TableCell>
                  {routeIds.map((id) => (
                    <TableCell
                      key={id}
                      align="right"
                      sx={{ fontWeight: id === pick ? 600 : 400, whiteSpace: 'nowrap' }}
                    >
                      {formatCriterion(row.criterion, row.values[id] ?? null)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
