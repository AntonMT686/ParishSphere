import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { alpha, useTheme } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import { Outlet } from 'react-router-dom';

/** Split-screen layout for sign-in pages: brand panel + form panel. */
export function AuthLayout() {
  const theme = useTheme();
  const { t } = useTranslation();
  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1.1fr 1fr' } }}>
      <Box
        sx={{
          display: { xs: 'none', md: 'flex' },
          flexDirection: 'column',
          justifyContent: 'flex-end',
          p: 6,
          color: '#fff',
          background: `linear-gradient(150deg, ${theme.palette.primary.dark} 0%, ${theme.palette.primary.main} 60%, ${alpha(theme.palette.secondary.main, 0.85)} 140%)`,
        }}
      >
        <Box component="img" src="/favicon.svg" alt="" sx={{ width: 56, height: 56, mb: 3 }} />
        <Typography variant="h1" sx={{ color: 'inherit', maxWidth: 480 }}>
          {t('app.name')}
        </Typography>
        <Typography sx={{ mt: 1.5, opacity: 0.9, maxWidth: 480, fontSize: 18 }}>{t('app.tagline')}</Typography>
      </Box>
      <Box sx={{ display: 'grid', placeItems: 'center', p: { xs: 2, sm: 4 }, bgcolor: 'background.default' }}>
        <Box sx={{ width: '100%', maxWidth: 420 }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
