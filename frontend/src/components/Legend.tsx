import { Box, Paper, Stack, Typography } from '@mui/material';
import { LEVELS, RISK, UNKNOWN } from '../lib/risk';

const ITEMS = [
  ...LEVELS.map((level) => ({
    color: RISK[level].color,
    label: RISK[level].label,
    code: RISK[level].code,
  })),
  { color: UNKNOWN.color, label: UNKNOWN.label, code: UNKNOWN.code },
];

function Dot({ color }: { color: string }) {
  return (
    <Box
      sx={{
        width: 14,
        height: 14,
        borderRadius: 0.75,
        bgcolor: color,
        border: '1px solid rgba(20,24,31,.35)',
        flexShrink: 0,
      }}
    />
  );
}

const panel = {
  position: 'absolute',
  top: 12,
  right: 12,
  border: 1,
  borderColor: 'divider',
  bgcolor: 'rgba(255,255,255,0.94)',
} as const;

export function Legend() {
  return (
    <>
      {/* Full legend on tablet and desktop */}
      <Paper
        elevation={0}
        sx={{ ...panel, p: 1.25, width: 148, display: { xs: 'none', sm: 'block' } }}
      >
        <Typography
          variant="overline"
          color="text.secondary"
          component="div"
          lineHeight={1.4}
          mb={0.5}
        >
          Weather risk
        </Typography>
        <Stack spacing={0.5}>
          {ITEMS.map((item) => (
            <Stack key={item.code} direction="row" alignItems="center" spacing={1}>
              <Dot color={item.color} />
              <Typography variant="caption" sx={{ flex: 1 }}>
                {item.label}
              </Typography>
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                {item.code}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Paper>
      {/* Compact strip on phones, where the map is small */}
      <Paper
        elevation={0}
        aria-label="Weather risk legend"
        sx={{ ...panel, px: 1, py: 0.75, display: { xs: 'flex', sm: 'none' }, gap: 1 }}
      >
        {ITEMS.map((item) => (
          <Stack
            key={item.code}
            direction="row"
            alignItems="center"
            spacing={0.5}
            title={item.label}
          >
            <Dot color={item.color} />
            <Typography variant="caption" fontWeight={600}>
              {item.code}
            </Typography>
          </Stack>
        ))}
      </Paper>
    </>
  );
}
