import FactCheckIcon from '@mui/icons-material/FactCheckOutlined';
import FamilyIcon from '@mui/icons-material/FamilyRestroomOutlined';
import GroupsIcon from '@mui/icons-material/GroupsOutlined';
import InsightsIcon from '@mui/icons-material/InsightsOutlined';
import PeopleIcon from '@mui/icons-material/PeopleAltOutlined';
import ReceiptIcon from '@mui/icons-material/ReceiptLongOutlined';
import ChurchIcon from '@mui/icons-material/ChurchOutlined';
import Avatar from '@mui/material/Avatar';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid2';
import { useTranslation } from 'react-i18next';
import { useTenantBranding } from '@/api/tenant';
import { EmptyState, PageHeader, StatCard } from '@/design-system';
import { useClergy } from '@/features/parish/api';

/** Role-based dashboard shell; live widgets are wired in T14 once module APIs exist. */
export function DashboardPage() {
  const { t } = useTranslation();
  const { data: branding, isLoading } = useTenantBranding();
  const { data: clergy } = useClergy();
  const parish = branding?.display_name ?? t('app.name');
  const stats = [
    { key: 'families', icon: <FamilyIcon />, tone: 'primary' as const },
    { key: 'members', icon: <PeopleIcon />, tone: 'info' as const },
    { key: 'anbiyam', icon: <GroupsIcon />, tone: 'secondary' as const },
    { key: 'societies', icon: <GroupsIcon />, tone: 'success' as const },
    { key: 'pendingApprovals', icon: <FactCheckIcon />, tone: 'warning' as const },
    { key: 'pendingFinance', icon: <ReceiptIcon />, tone: 'error' as const },
  ];
  return (
    <>
      <PageHeader title={t('dashboard.greeting', { parish })} subtitle={branding?.diocese_name} />
      <Grid container spacing={2}>
        {clergy && (clergy.parish_priest || clergy.others.length > 0) && (
          <Grid size={12}>
            <Card>
              <CardContent>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={{ xs: 1.5, md: 4 }} alignItems={{ md: 'center' }}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Avatar sx={{ bgcolor: 'primary.main' }}><ChurchIcon /></Avatar>
                    <div>
                      <Typography variant="caption" color="text.secondary">{t('priests.role.PARISH_PRIEST')}</Typography>
                      <Typography variant="subtitle1" fontWeight={600}>{clergy.parish_priest?.name ?? '—'}</Typography>
                    </div>
                  </Stack>
                  {clergy.others.map((o) => (
                    <div key={`${o.id}-${o.role}`}>
                      <Typography variant="caption" color="text.secondary">{t(`priests.role.${o.role}`)}</Typography>
                      <Typography variant="body2">{o.name}</Typography>
                    </div>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        )}
        {stats.map((s) => (
          <Grid key={s.key} size={{ xs: 12, sm: 6, lg: 4, xl: 2 }}>
            <StatCard label={t(`dashboard.${s.key}`)} value="—" icon={s.icon} tone={s.tone} loading={isLoading} />
          </Grid>
        ))}
        <Grid size={12}>
          <Card>
            <EmptyState icon={<InsightsIcon />} title={t('nav.dashboard')} description={t('dashboard.comingSoon')} />
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
