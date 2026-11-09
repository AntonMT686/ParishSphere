/** Design tokens – single source of truth for colours, radii and typography (docs/07-ui-ux-navigation.md). */
export const palette = {
  light: {
    primary: '#2F3E9E',
    secondary: '#B8860B',
    success: '#2E7D32',
    warning: '#ED6C02',
    error: '#C62828',
    info: '#0277BD',
    background: '#F6F7FB',
    paper: '#FFFFFF',
    textPrimary: '#1B1F3B',
    textSecondary: '#5B6075',
    divider: '#E4E6EF',
  },
  dark: {
    primary: '#8C9EFF',
    secondary: '#E0B54A',
    success: '#66BB6A',
    warning: '#FFA726',
    error: '#EF5350',
    info: '#4FC3F7',
    background: '#0F1220',
    paper: '#171B2E',
    textPrimary: '#E8EAF6',
    textSecondary: '#A7ABC3',
    divider: '#2A2F48',
  },
} as const;

export const radius = { card: 12, control: 8 } as const;

export const fontFamily = ['Inter', '"Noto Sans Tamil"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'].join(
  ',',
);
