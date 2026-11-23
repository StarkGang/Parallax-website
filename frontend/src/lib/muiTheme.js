import { alpha, createTheme } from '@mui/material/styles';

/**
 * Material UI theme for the Parallax portals.
 *
 * The convention already runs on a dark editorial system, so the MUI theme is
 * tuned to it rather than shipping stock Material: deep navy surfaces, the
 * site's violet/cyan accents, softly rounded cards and flat (no glow) elevation.
 */
export const SURFACE = {
  base: '#06080e',
  paper: '#0b1120',
  raised: '#101a2e',
  line: 'rgba(148, 170, 205, 0.16)',
  text: '#e8eefc',
  muted: '#93a4c6',
  accent: '#7c5cff',
  cyan: '#38bdf8',
};

const sans =
  "var(--sans, 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif)";
const display = "var(--display, 'Space Grotesk', var(--sans, sans-serif))";
const mono = "var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace)";

export const muiTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: SURFACE.accent, light: '#a58cff', dark: '#5b3fe0', contrastText: '#ffffff' },
    secondary: { main: SURFACE.cyan, contrastText: '#04121c' },
    success: { main: '#3ddc97' },
    warning: { main: '#fbbf24' },
    error: { main: '#f87171' },
    info: { main: SURFACE.cyan },
    background: { default: SURFACE.base, paper: SURFACE.paper },
    text: { primary: SURFACE.text, secondary: SURFACE.muted },
    divider: SURFACE.line,
  },
  shape: { borderRadius: 14 },
  typography: {
    fontFamily: sans,
    h1: { fontFamily: display, fontWeight: 700, letterSpacing: '-0.03em' },
    h2: { fontFamily: display, fontWeight: 700, letterSpacing: '-0.02em' },
    h3: { fontFamily: display, fontWeight: 700, letterSpacing: '-0.02em', fontSize: '1.15rem' },
    h4: { fontFamily: display, fontWeight: 700, fontSize: '1rem' },
    h5: { fontFamily: display, fontWeight: 600, fontSize: '0.95rem' },
    h6: { fontFamily: display, fontWeight: 600, fontSize: '0.875rem' },
    subtitle1: { fontWeight: 600, fontSize: '0.9rem' },
    subtitle2: { fontWeight: 600, fontSize: '0.8rem', letterSpacing: '0.02em' },
    body1: { fontSize: '0.875rem', lineHeight: 1.6 },
    body2: { fontSize: '0.8125rem', lineHeight: 1.6 },
    caption: { fontSize: '0.72rem', color: SURFACE.muted },
    button: { textTransform: 'none', fontWeight: 600, letterSpacing: '0.01em' },
    overline: {
      fontFamily: mono,
      fontSize: '0.625rem',
      letterSpacing: '0.16em',
      fontWeight: 600,
      lineHeight: 1.6,
    },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none' },
        outlined: { borderColor: SURFACE.line },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        // Material 3 filled button: flat fill, 40dp height, state layer on
        // hover instead of a gradient glow.
        root: {
          borderRadius: 999,
          minWidth: 0,
          minHeight: 40,
          paddingInline: 24,
          paddingBlock: 10,
          fontSize: '0.875rem',
          fontWeight: 500,
          letterSpacing: '0.1px',
          lineHeight: 1.4,
          gap: 8,
          whiteSpace: 'nowrap',
          boxShadow: 'none',
          transition:
            'background-color 150ms cubic-bezier(.2,0,0,1), box-shadow 150ms cubic-bezier(.2,0,0,1), border-color 150ms cubic-bezier(.2,0,0,1)',
          '&:focus-visible': {
            outline: `2px solid ${SURFACE.cyan}`,
            outlineOffset: 2,
            boxShadow: 'none',
          },
          '&.Mui-disabled': { opacity: 0.38, boxShadow: 'none' },
          '& .MuiButton-endIcon': { marginLeft: 2, marginRight: -4 },
          '& .MuiButton-startIcon': { marginLeft: -4, marginRight: 2 },
        },
        // Compact buttons are rounded rectangles, not pills: dense admin
        // toolbars and table rows read as a row of labels otherwise.
        sizeSmall: {
          minHeight: 32,
          paddingInline: 14,
          paddingBlock: 6,
          borderRadius: 10,
          fontSize: '0.8125rem',
        },
        sizeLarge: { minHeight: 48, paddingInline: 28, paddingBlock: 12, fontSize: '0.9375rem' },
        contained: {
          backgroundColor: SURFACE.accent,
          backgroundImage: 'none',
          color: '#ffffff',
          '&:hover': { backgroundColor: '#8769ff', boxShadow: '0 1px 2px rgba(0,0,0,0.30)' },
          '&:active': { backgroundColor: '#8c70ff' },
          // Colour-specific variants must be nested on the slot: keys like
          // `containedError` are ignored by MUI and left danger buttons purple.
          '&.MuiButton-colorError': {
            backgroundColor: '#f87171',
            backgroundImage: 'none',
            color: '#1b0707',
          },
          '&.MuiButton-colorError:hover': { backgroundColor: '#f97c7c' },
          '&.MuiButton-colorError:active': { backgroundColor: '#ef5f5f' },
          '&.MuiButton-colorSecondary': {
            backgroundColor: SURFACE.cyan,
            backgroundImage: 'none',
            color: '#04121c',
          },
          '&.MuiButton-colorSecondary:hover': { backgroundColor: '#48c2f9' },
        },
        outlined: {
          borderColor: alpha('#c7c9d3', 0.42),
          backgroundColor: 'transparent',
          color: SURFACE.text,
          '&:hover': {
            borderColor: alpha(SURFACE.accent, 0.85),
            backgroundColor: alpha(SURFACE.accent, 0.08),
          },
          '&:active': { backgroundColor: alpha(SURFACE.accent, 0.12) },
        },
        text: { color: alpha(SURFACE.text, 0.82), '&:hover': { backgroundColor: alpha('#ffffff', 0.06) } },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: { borderRadius: 12, border: `1px solid ${SURFACE.line}`, padding: 7 },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 999, fontWeight: 600, fontSize: '0.72rem' },
        sizeSmall: { height: 22 },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { backgroundImage: 'none', borderRadius: 20 },
      },
    },
    MuiSwitch: {
      styleOverrides: { root: { padding: 8 }, thumb: { boxShadow: 'none' } },
    },
    MuiTableContainer: {
      styleOverrides: { root: { borderRadius: 16 } },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 12, fontSize: '0.8125rem', alignItems: 'center' },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { fontSize: '0.72rem', borderRadius: 8, backgroundColor: SURFACE.raised },
      },
    },
  },
});

export default muiTheme;
