import { alpha, createTheme, type PaletteMode, type Theme } from '@mui/material/styles';
import { fontFamily, palette, radius } from './tokens';

export function buildTheme(mode: PaletteMode, primaryOverride?: string | null): Theme {
  const p = palette[mode];
  const primary = primaryOverride || p.primary;
  return createTheme({
    palette: {
      mode,
      primary: { main: primary },
      secondary: { main: p.secondary },
      success: { main: p.success },
      warning: { main: p.warning },
      error: { main: p.error },
      info: { main: p.info },
      background: { default: p.background, paper: p.paper },
      text: { primary: p.textPrimary, secondary: p.textSecondary },
      divider: p.divider,
    },
    shape: { borderRadius: radius.control },
    typography: {
      fontFamily,
      h1: { fontSize: '2rem', fontWeight: 600 },
      h2: { fontSize: '1.5rem', fontWeight: 600 },
      h3: { fontSize: '1.25rem', fontWeight: 600 },
      h4: { fontSize: '1.125rem', fontWeight: 600 },
      subtitle1: { fontWeight: 500 },
      button: { textTransform: 'none', fontWeight: 600 },
    },
    components: {
      MuiCard: {
        defaultProps: { variant: 'outlined' },
        styleOverrides: { root: { borderRadius: radius.card, borderColor: p.divider } },
      },
      MuiPaper: { styleOverrides: { rounded: { borderRadius: radius.card } } },
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiTextField: { defaultProps: { size: 'small', fullWidth: true } },
      MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
      MuiListItemButton: {
        styleOverrides: {
          root: {
            borderRadius: radius.control,
            '&.Mui-selected': { backgroundColor: alpha(primary, 0.12), color: primary },
            '&.Mui-selected .MuiListItemIcon-root': { color: primary },
          },
        },
      },
    },
  });
}
