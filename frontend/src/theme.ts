import { createTheme } from '@mui/material/styles';
import { RISK_COLORS } from './lib/risk';

declare module '@mui/material/styles' {
  interface Palette {
    risk: typeof RISK_COLORS;
  }
  interface PaletteOptions {
    risk?: typeof RISK_COLORS;
  }
}

const FONT = '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#2453c7' },
    success: { main: '#23843d' },
    warning: { main: '#b35c00' },
    error: { main: '#c62f28' },
    background: { default: '#f4f6f8', paper: '#ffffff' },
    text: { primary: '#14181f', secondary: '#566070' },
    divider: '#e2e6eb',
    risk: RISK_COLORS,
  },
  shape: { borderRadius: 10 },
  spacing: 8,
  typography: {
    fontFamily: FONT,
    h1: { fontSize: '1.2rem', fontWeight: 700, letterSpacing: '-0.01em' },
    h2: { fontSize: '1rem', fontWeight: 600 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    body2: { lineHeight: 1.5 },
    caption: { lineHeight: 1.4 },
    overline: { fontWeight: 600, letterSpacing: '0.06em', lineHeight: 1.6 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { fontVariantNumeric: 'tabular-nums' },
        '.maplibregl-popup-content': { padding: 0, borderRadius: 10, boxShadow: 'none' },
      },
    },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiCard: { defaultProps: { variant: 'outlined' } },
    MuiTextField: { defaultProps: { size: 'small', fullWidth: true } },
    MuiToggleButton: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } } },
    MuiAlert: { styleOverrides: { root: { alignItems: 'flex-start' } } },
    MuiTooltip: { defaultProps: { arrow: true } },
  },
});
