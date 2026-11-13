import { useTheme } from '@mui/material/styles';

/**
 * Categorical series colours (fixed order, never cycled), stepped separately for light and dark surfaces.
 * Validated palette: blue, orange, aqua — the first three pass all-pairs CVD checks in both modes.
 */
const SERIES = { light: ['#2a78d6', '#eb6834', '#1baf7a'], dark: ['#3987e5', '#d95926', '#199e70'] };

export function useSeries(): string[] {
  return SERIES[useTheme().palette.mode];
}

/** Recessive axes / grid and a themed tooltip shared by every dashboard chart. */
export function useChartStyle() {
  const theme = useTheme();
  return {
    axis: { fontSize: 12, fill: theme.palette.text.secondary },
    grid: theme.palette.divider,
    tooltip: {
      contentStyle: { background: theme.palette.background.paper, border: `1px solid ${theme.palette.divider}`, borderRadius: 8, fontSize: 13 },
      labelStyle: { color: theme.palette.text.primary, fontWeight: 600 },
      itemStyle: { color: theme.palette.text.primary },
      cursor: { fill: theme.palette.action.hover },
    },
  };
}

/** Compact rupee axis labels: ₹1.2L, ₹45K. */
export function shortInr(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(0)}K`;
  return `₹${v}`;
}
