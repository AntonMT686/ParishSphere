import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { useCan } from '@/auth/authStore';
import { ActionStatus } from '@/features/activities/ActionItems';
import { actKeys, fetchMeetings, useActionItems } from '@/features/activities/api';
import { formatDate, formatWallTime } from '@/lib/format';

/** Upcoming meetings and the user's open action items. */
export function DashboardAgenda() {
  const { t } = useTranslation();
  const can = useCan();
  const seeMeetings = can('meeting.view');
  const { data: meetings } = useQuery({
    queryKey: [...actKeys.meetings, 'dashboard'],
    queryFn: () => fetchMeetings({ page: 1, size: 5, sort: 'scheduled_at' }, { when: 'upcoming' }),
    enabled: seeMeetings,
  });
  const { data: actions } = useActionItems({ mine: true, status: 'ACTIVE' });
  const items = actions?.items.slice(0, 5) ?? [];
  return (
    <>
      {seeMeetings && (
        <Grid size={{ xs: 12, md: 6 }}>
          <Card sx={{ height: '100%' }}>
            <CardHeader title={t('dashboard.upcomingMeetings')} action={<Button size="small" component={RouterLink} to="/meetings">{t('dashboard.viewAll')}</Button>} />
            <CardContent sx={{ pt: 0 }}>
              {meetings?.items.length === 0 && <Typography variant="body2" color="text.secondary">{t('meetings.noneUpcoming')}</Typography>}
              <Stack spacing={1.25} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t('dashboard.upcomingMeetings')}>
                {meetings?.items.map((m) => (
                  <Box component="li" key={m.id}>
                    <Typography component={RouterLink} to={`/meetings/${m.id}`} variant="body2" fontWeight={600} sx={{ color: 'text.primary', textDecoration: 'none' }}>{m.title}</Typography>
                    <Typography variant="caption" color="text.secondary" component="div">
                      {formatWallTime(m.scheduled_at)} · {m.org_unit?.name ?? t('activities.parishLevel')}{m.location ? ` · ${m.location}` : ''}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      )}
      <Grid size={{ xs: 12, md: seeMeetings ? 6 : 12 }}>
        <Card sx={{ height: '100%' }}>
          <CardHeader title={t('dashboard.myActionItems')} action={<Button size="small" component={RouterLink} to="/action-items">{t('dashboard.viewAll')}</Button>} />
          <CardContent sx={{ pt: 0 }}>
            {actions && items.length === 0 && <Typography variant="body2" color="text.secondary">{t('actions.noneMine')}</Typography>}
            <Stack spacing={1.25} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t('dashboard.myActionItems')}>
              {items.map((a) => (
                <Stack component="li" key={a.id} direction="row" spacing={1} alignItems="center">
                  <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                    <Typography component={RouterLink} to={`/action-items?open=${a.id}`} variant="body2" fontWeight={600} noWrap
                      sx={{ display: 'block', color: 'text.primary', textDecoration: 'none' }}>{a.title}</Typography>
                    <Typography variant="caption" color={a.overdue ? 'error' : 'text.secondary'}>
                      {a.due_date ? t('actions.dueOn', { date: formatDate(a.due_date) }) : t('actions.noDue')}
                    </Typography>
                  </Box>
                  <ActionStatus item={a} />
                </Stack>
              ))}
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </>
  );
}
