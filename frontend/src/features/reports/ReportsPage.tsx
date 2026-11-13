import AssessmentIcon from '@mui/icons-material/AssessmentOutlined';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Grid from '@mui/material/Grid2';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { EmptyState, PageHeader } from '@/design-system';
import { GROUPS, useReportCatalog } from './api';

/** Report catalog: only the reports the user may run, grouped like the brief (parish, activity, finance, management). */
export function ReportsPage() {
  const { t } = useTranslation();
  const { data = [], isLoading } = useReportCatalog();
  return (
    <>
      <PageHeader title={t('reports.title')} subtitle={t('reports.subtitle')} breadcrumbs={[{ label: t('reports.title') }]} />
      {!isLoading && data.length === 0 && <Card><EmptyState icon={<AssessmentIcon />} title={t('reports.none')} description={t('reports.noneHint')} /></Card>}
      {GROUPS.map((g) => {
        const items = data.filter((r) => r.group === g);
        if (!items.length) return null;
        return (
          <section key={g} aria-labelledby={`rg-${g}`}>
            <Typography id={`rg-${g}`} variant="h3" sx={{ mt: 3, mb: 1.5 }}>{t(`reports.group.${g}`)}</Typography>
            <Grid container spacing={2}>
              {items.map((r) => (
                <Grid key={r.code} size={{ xs: 12, sm: 6, lg: 4 }}>
                  <Card sx={{ height: '100%' }}>
                    <CardActionArea component={RouterLink} to={`/reports/${r.code}`} sx={{ height: '100%', alignItems: 'flex-start', display: 'flex' }}>
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight={600} gutterBottom>{t(`reports.r.${r.code}.title`, r.title)}</Typography>
                        <Typography variant="body2" color="text.secondary">{t(`reports.r.${r.code}.desc`, r.description)}</Typography>
                      </CardContent>
                    </CardActionArea>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </section>
        );
      })}
    </>
  );
}
