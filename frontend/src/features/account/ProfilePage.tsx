import DevicesIcon from '@mui/icons-material/DevicesOutlined';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid2';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import type { NotificationPreference, SessionOut } from '@/api/types';
import { useAuthStore } from '@/auth/authStore';
import { PageHeader, useFeedback } from '@/design-system';
import { ChangePasswordForm } from '@/features/auth/ChangePasswordForm';
import { formatDateTime } from '@/lib/format';

function Detail({ label, value }: { label: string; value?: string | null }) {
  return (
    <Stack direction="row" spacing={2} sx={{ py: 0.75 }}>
      <Typography color="text.secondary" sx={{ width: 140, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography>{value || '—'}</Typography>
    </Stack>
  );
}

function SessionsCard() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toastError, confirm } = useFeedback();
  const logout = useAuthStore((s) => s.logout);
  const { data } = useQuery({ queryKey: ['auth', 'sessions'], queryFn: async () => (await api.get<SessionOut[]>('/auth/sessions')).data });
  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/auth/sessions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auth', 'sessions'] }),
    onError: toastError,
  });
  return (
    <Card>
      <CardHeader
        title={t('profile.sessions')}
        action={
          <Button
            color="error"
            onClick={async () => {
              if (await confirm({ title: t('common.signOutAll'), message: t('profile.signOutAllConfirm'), destructive: true })) {
                await logout('logout', { everywhere: true });
              }
            }}
          >
            {t('common.signOutAll')}
          </Button>
        }
      />
      <List dense>
        {(data ?? []).map((s) => (
          <ListItem
            key={s.id}
            secondaryAction={
              s.current ? (
                <Chip size="small" color="primary" label={t('profile.thisDevice')} />
              ) : (
                <Button size="small" onClick={() => revoke.mutate(s.id)}>
                  {t('profile.revoke')}
                </Button>
              )
            }
          >
            <ListItemIcon>
              <DevicesIcon />
            </ListItemIcon>
            <ListItemText
              primary={s.user_agent?.slice(0, 80) || 'Unknown device'}
              secondary={`${s.ip ?? ''} · ${t('profile.lastActive')}: ${formatDateTime(s.last_activity_at)}`}
            />
          </ListItem>
        ))}
      </List>
    </Card>
  );
}

function PreferencesCard() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toastError } = useFeedback();
  const { data } = useQuery({
    queryKey: ['notifications', 'preferences'],
    queryFn: async () => (await api.get<NotificationPreference[]>('/notifications/preferences')).data,
  });
  const save = useMutation({
    mutationFn: (p: { event_code: string; channel: string; enabled: boolean }) => api.put('/notifications/preferences', [p]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications', 'preferences'] }),
    onError: toastError,
  });
  const events = new Map<string, { description: string; IN_APP?: boolean; EMAIL?: boolean }>();
  for (const p of data ?? []) {
    const e = events.get(p.event_code) ?? { description: p.description };
    e[p.channel as 'IN_APP' | 'EMAIL'] = p.enabled;
    events.set(p.event_code, e);
  }
  return (
    <Card>
      <CardHeader title={t('profile.preferences')} />
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{t('profile.event')}</TableCell>
            <TableCell align="center">{t('profile.inApp')}</TableCell>
            <TableCell align="center">{t('profile.emailChannel')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {[...events.entries()].map(([code, e]) => (
            <TableRow key={code}>
              <TableCell>{e.description}</TableCell>
              {(['IN_APP', 'EMAIL'] as const).map((ch) => (
                <TableCell key={ch} align="center">
                  <Switch
                    size="small"
                    checked={Boolean(e[ch])}
                    inputProps={{ 'aria-label': `${code} ${ch}` }}
                    onChange={(_, enabled) => save.mutate({ event_code: code, channel: ch, enabled })}
                  />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

export function ProfilePage() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  return (
    <>
      <PageHeader title={t('common.profile')} breadcrumbs={[{ label: t('nav.dashboard'), to: '/' }, { label: t('common.profile') }]} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card sx={{ height: '100%' }}>
            <CardHeader title={t('profile.details')} />
            <CardContent sx={{ pt: 0 }}>
              <Detail label={t('users.fullName')} value={user?.full_name} />
              <Detail label={t('common.username')} value={user?.username} />
              <Detail label={t('common.email')} value={user?.email} />
              <Detail label={t('common.phone')} value={user?.phone} />
              <Stack direction="row" spacing={2} sx={{ py: 0.75 }}>
                <Typography color="text.secondary" sx={{ width: 140, flexShrink: 0 }}>
                  {t('common.roles')}
                </Typography>
                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                  {(user?.roles ?? []).map((r) => (
                    <Chip key={r} size="small" label={r.replace(/_/g, ' ')} />
                  ))}
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card sx={{ height: '100%' }}>
            <CardHeader title={t('profile.security')} />
            <CardContent sx={{ pt: 0 }}>
              <ChangePasswordForm />
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <SessionsCard />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <PreferencesCard />
        </Grid>
      </Grid>
    </>
  );
}
