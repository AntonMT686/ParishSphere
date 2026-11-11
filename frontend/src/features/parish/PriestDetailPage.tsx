import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/EditOutlined';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { Priest, PriestAssignment, UserLookup } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { EmptyState, PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { UserPicker } from '@/features/org/pickers';
import { formatDate } from '@/lib/format';
import { parishKeys, PRIEST_ROLES, PRIEST_STATUSES, usePriest } from './api';
import { PriestDialog } from './PriestDialog';

const today = () => new Date().toISOString().slice(0, 10);

function usePriestMutation<T>(fn: (v: T) => Promise<unknown>, onDone?: () => void) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast, toastError } = useFeedback();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: parishKeys.priests });
      void qc.invalidateQueries({ queryKey: ['parish'] });
      toast(t('common.saved'));
      onDone?.();
    },
    onError: toastError,
  });
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Grid container spacing={1} sx={{ py: 0.75 }}>
      <Grid size={{ xs: 12, sm: 4 }}><Typography variant="body2" color="text.secondary">{label}</Typography></Grid>
      <Grid size={{ xs: 12, sm: 8 }}><Typography variant="body2" component="div">{children ?? '—'}</Typography></Grid>
    </Grid>
  );
}

export function PriestDetailPage() {
  const { priestId = '' } = useParams();
  const { t } = useTranslation();
  const can = useCan();
  const { confirm } = useFeedback();
  const { data: p, isError } = usePriest(priestId);
  const [editing, setEditing] = useState(false);
  const [appointing, setAppointing] = useState(false);
  const [relieving, setRelieving] = useState<PriestAssignment | null>(null);
  const [linking, setLinking] = useState(false);
  const setStatus = usePriestMutation((status: string) => api.post(`/priests/${priestId}/status`, { status }));

  if (isError) return <EmptyState title={t('errors.NOT_FOUND')} />;
  if (!p) return <Skeleton variant="rounded" height={420} />;
  const canUpdate = can('priest.update');
  const active = p.status === 'ACTIVE';
  const changeStatus = async (s: string) => {
    if (s === p.status) return;
    const ok = await confirm({
      title: t('priests.changeStatus'),
      message: s === 'ACTIVE' ? undefined : t('priests.statusWarning'),
      destructive: s !== 'ACTIVE',
    });
    if (ok) setStatus.mutate(s);
  };

  return (
    <>
      <PageHeader
        title={p.display_name}
        subtitle={p.name_local ?? undefined}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('nav.priests'), to: '/admin/priests' }, { label: p.full_name }]}
        actions={canUpdate && (
          <Stack direction="row" spacing={1}>
            <TextField select size="small" label={t('common.status')} value={p.status} onChange={(e) => void changeStatus(e.target.value)} sx={{ minWidth: 140 }}>
              {PRIEST_STATUSES.map((s) => <MenuItem key={s} value={s}>{t(`status.${s}`, { defaultValue: s })}</MenuItem>)}
            </TextField>
            <Button startIcon={<EditIcon />} onClick={() => setEditing(true)}>{t('common.edit')}</Button>
          </Stack>
        )}
      />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('priests.details')} action={<StatusBadge status={p.status} />} />
            <CardContent sx={{ pt: 0 }}>
              <Row label={t('priests.clergyType')}>{t(`priests.clergy.${p.clergy_type}`)}</Row>
              {p.clergy_type === 'RELIGIOUS'
                ? <Row label={t('priests.congregation')}>{p.congregation}</Row>
                : <Row label={t('priests.homeDiocese')}>{p.home_diocese}</Row>}
              <Row label={t('people.dob')}>{p.date_of_birth && formatDate(p.date_of_birth)}</Row>
              <Row label={t('priests.ordination')}>{p.ordination_date && formatDate(p.ordination_date)}</Row>
              <Row label={t('common.phone')}>{p.phone}</Row>
              <Row label={t('common.email')}>{p.email}</Row>
              <Row label={t('common.remarks')}>{p.remarks}</Row>
            </CardContent>
          </Card>
          <Card>
            <CardHeader title={t('priests.account')}
              action={canUpdate && can('user.assign_role') && <Button size="small" onClick={() => setLinking(true)}>{p.user ? t('priests.changeAccount') : t('priests.linkAccount')}</Button>} />
            <CardContent sx={{ pt: 0 }}>
              {p.user
                ? <Typography variant="body2">{p.user.full_name} <Typography component="span" variant="body2" color="text.secondary">({p.user.username})</Typography></Typography>
                : <Typography variant="body2" color="text.secondary">{t('priests.noAccount')}</Typography>}
              <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1 }}>{t('priests.accountHint')}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card>
            <CardHeader title={t('priests.assignments')}
              action={canUpdate && active && <Button size="small" startIcon={<AddIcon />} onClick={() => setAppointing(true)}>{t('priests.appoint')}</Button>} />
            <CardContent sx={{ pt: 0 }}>
              {p.assignments.length === 0 ? (
                <Typography variant="body2" color="text.secondary">{t('priests.noAssignments')}</Typography>
              ) : (
                <Table size="small" aria-label={t('priests.assignments')}>
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('priests.roleLabel')}</TableCell>
                      <TableCell>{t('priests.from')}</TableCell>
                      <TableCell>{t('priests.until')}</TableCell>
                      <TableCell />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {p.assignments.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell>
                          <Stack direction="row" spacing={1} alignItems="center">
                            <span>{t(`priests.role.${a.role}`)}</span>
                            {a.current && <Chip size="small" color="success" label={t('priests.current')} />}
                          </Stack>
                          {a.responsibilities && <Typography variant="caption" color="text.secondary" component="div">{a.responsibilities}</Typography>}
                          {a.appointment_ref && <Typography variant="caption" color="text.secondary" component="div">{t('priests.ref')}: {a.appointment_ref}</Typography>}
                        </TableCell>
                        <TableCell>{formatDate(a.appointed_on)}</TableCell>
                        <TableCell>
                          {a.relieved_on ? formatDate(a.relieved_on) : '—'}
                          {a.relieving_reason && <Typography variant="caption" color="text.secondary" component="div">{a.relieving_reason}</Typography>}
                        </TableCell>
                        <TableCell align="right">
                          {canUpdate && (!a.relieved_on || a.relieved_on > today()) && (
                            <Button size="small" color="warning" onClick={() => setRelieving(a)}>{t('priests.relieve')}</Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1.5 }}>{t('priests.untilHint')}</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      <PriestDialog open={editing} onClose={() => setEditing(false)} priest={p} />
      <AppointDialog open={appointing} onClose={() => setAppointing(false)} priest={p} />
      <RelieveDialog assignment={relieving} onClose={() => setRelieving(null)} priest={p} />
      <LinkUserDialog open={linking} onClose={() => setLinking(false)} priest={p} />
    </>
  );
}

function AppointDialog({ open, onClose, priest }: { open: boolean; onClose: () => void; priest: Priest }) {
  const { t } = useTranslation();
  const [role, setRole] = useState<string>('ASSISTANT_PRIEST');
  const [from, setFrom] = useState(today());
  const [until, setUntil] = useState('');
  const [resp, setResp] = useState('');
  const [ref, setRef] = useState('');
  const [relieveCurrent, setRelieveCurrent] = useState(false);
  useEffect(() => {
    if (open) { setRole('ASSISTANT_PRIEST'); setFrom(today()); setUntil(''); setResp(''); setRef(''); setRelieveCurrent(false); }
  }, [open]);
  const appoint = usePriestMutation(() => api.post(`/priests/${priest.id}/assignments`, {
    role, appointed_on: from, relieved_on: until || null, responsibilities: resp || null, appointment_ref: ref || null,
    relieve_current: role === 'PARISH_PRIEST' && relieveCurrent,
  }), onClose);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('priests.appointTitle', { name: priest.display_name })}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField select label={t('priests.roleLabel')} value={role} onChange={(e) => setRole(e.target.value)}>
            {PRIEST_ROLES.map((r) => <MenuItem key={r} value={r}>{t(`priests.role.${r}`)}</MenuItem>)}
          </TextField>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField type="date" label={t('priests.from')} value={from} onChange={(e) => setFrom(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
            <TextField type="date" label={t('priests.untilOptional')} value={until} onChange={(e) => setUntil(e.target.value)} slotProps={{ inputLabel: { shrink: true } }}
              helperText={t('priests.handoverHint')} fullWidth />
          </Stack>
          <TextField label={t('priests.responsibilities')} value={resp} onChange={(e) => setResp(e.target.value)} multiline minRows={2} />
          <TextField label={t('priests.ref')} value={ref} onChange={(e) => setRef(e.target.value)} />
          {role === 'PARISH_PRIEST' && (
            <>
              <Alert severity="info">{t('priests.parishPriestInfo')}</Alert>
              <FormControlLabel control={<Checkbox checked={relieveCurrent} onChange={(e) => setRelieveCurrent(e.target.checked)} />}
                label={t('priests.relieveCurrent', { date: from ? formatDate(from) : '' })} />
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!from || appoint.isPending} onClick={() => appoint.mutate(undefined)}>{t('priests.appoint')}</Button>
      </DialogActions>
    </Dialog>
  );
}

function RelieveDialog({ assignment, onClose, priest }: { assignment: PriestAssignment | null; onClose: () => void; priest: Priest }) {
  const { t } = useTranslation();
  const [on, setOn] = useState(today());
  const [reason, setReason] = useState('');
  useEffect(() => { if (assignment) { setOn(today()); setReason(''); } }, [assignment]);
  const relieve = usePriestMutation(() => api.post(`/priests/${priest.id}/assignments/${assignment?.id}/relieve`, {
    relieved_on: on, reason: reason || null,
  }), onClose);
  return (
    <Dialog open={Boolean(assignment)} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t('priests.relieveTitle')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2">{assignment && `${priest.display_name} · ${t(`priests.role.${assignment.role}`)}`}</Typography>
          <TextField type="date" label={t('priests.handoverDate')} value={on} onChange={(e) => setOn(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }} helperText={t('priests.handoverHint')} />
          <TextField label={t('priests.reason')} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t('priests.reasonPlaceholder')} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" color="warning" disabled={!on || relieve.isPending} onClick={() => relieve.mutate(undefined)}>{t('priests.relieve')}</Button>
      </DialogActions>
    </Dialog>
  );
}

function LinkUserDialog({ open, onClose, priest }: { open: boolean; onClose: () => void; priest: Priest }) {
  const { t } = useTranslation();
  const [user, setUser] = useState<UserLookup | null>(null);
  useEffect(() => { if (open) setUser(null); }, [open]);
  const link = usePriestMutation((userId: string | null) => api.post(`/priests/${priest.id}/user`, { user_id: userId }), onClose);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('priests.linkAccount')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Alert severity="info">{t('priests.accountHint')}</Alert>
          <UserPicker label={t('priests.userAccount')} value={user} onChange={setUser} />
        </Stack>
      </DialogContent>
      <DialogActions>
        {priest.user && <Button color="error" sx={{ mr: 'auto' }} disabled={link.isPending} onClick={() => link.mutate(null)}>{t('priests.unlink')}</Button>}
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!user || link.isPending} onClick={() => link.mutate(user?.id ?? null)}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}
