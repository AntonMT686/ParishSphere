import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { useCan } from '@/auth/authStore';
import { useBoard } from '@/features/notices/api';
import { NoticeCard } from '@/features/notices/NoticeCard';

/** The three most relevant live notices (important ones first). */
export function DashboardNotices() {
  const { t } = useTranslation();
  const can = useCan();
  const enabled = can('notice.view');
  const { data } = useBoard('', '', 3);
  if (!enabled || !data || data.items.length === 0) return null;
  return (
    <Grid size={12}>
      <Stack direction="row" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h3">{t('dashboard.notices')}</Typography>
        <Button size="small" component={RouterLink} to="/notices" sx={{ ml: 'auto' }}>{t('dashboard.viewAll')}</Button>
      </Stack>
      <Grid container spacing={2}>
        {data.items.map((n) => <Grid key={n.id} size={{ xs: 12, md: 4 }}><NoticeCard n={n} compact /></Grid>)}
      </Grid>
    </Grid>
  );
}
