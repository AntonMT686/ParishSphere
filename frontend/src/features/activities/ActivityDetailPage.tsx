import EditIcon from '@mui/icons-material/EditOutlined';
import SendIcon from '@mui/icons-material/SendOutlined';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid2';
import InputAdornment from '@mui/material/InputAdornment';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { Activity } from '@/api/types';
import { EmptyState, PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { wfKeys } from '@/features/workflow/api';
import { formatDate, formatDateTime, formatMoney } from '@/lib/format';
import { ActionItemsCard } from './ActionItems';
import { actKeys, useActivity } from './api';
import { ApprovalSection, AttachmentsCard, Fact } from './shared';

function SubmitDialog({ activity, open, onClose }: { activity: Activity; open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const [comment, setComment] = useState('');
  const submit = useMutation({
    mutationFn: async () => (await api.post<Activity>(`/activities/${activity.id}/submit`, { comment: comment.trim() || null })).data,
    onSuccess: (a) => {
      qc.setQueryData([...actKeys.activities, a.id], a);
      void qc.invalidateQueries({ queryKey: actKeys.activities });
      void qc.invalidateQueries({ queryKey: wfKeys.all });
      toast(t('activities.submitted'));
      onClose();
    },
    onError: toastError,
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{activity.status === 'REWORK' ? t('activities.resubmit') : t('activities.submit')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>{t('activities.submitHint')}</Typography>
        <TextField label={t('workflow.comment')} value={comment} onChange={(e) => setComment(e.target.value)} multiline minRows={2} fullWidth />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={submit.isPending} onClick={() => submit.mutate()}>{t('activities.send')}</Button>
      </DialogActions>
    </Dialog>
  );
}

function CompleteDialog({ activity, open, onClose }: { activity: Activity; open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const [details, setDetails] = useState(activity.actual_details ?? '');
  const [amount, setAmount] = useState(activity.actual_amount ?? '');
  const [count, setCount] = useState(activity.participant_count?.toString() ?? '');
  const complete = useMutation({
    mutationFn: async () => (await api.post<Activity>(`/activities/${activity.id}/complete`, {
      actual_details: details.trim(), actual_amount: amount === '' ? null : amount, participant_count: count === '' ? null : Number(count),
    })).data,
    onSuccess: (a) => { qc.setQueryData([...actKeys.activities, a.id], a); void qc.invalidateQueries({ queryKey: actKeys.activities }); toast(t('activities.completed')); onClose(); },
    onError: toastError,
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('activities.recordCompletion')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField label={t('activities.actual')} value={details} onChange={(e) => setDetails(e.target.value)} multiline minRows={3} required />
          <Stack direction="row" spacing={2}>
            <TextField type="number" label={t('activities.actualAmount')} value={amount} onChange={(e) => setAmount(e.target.value)}
              slotProps={{ input: { startAdornment: <InputAdornment position="start">₹</InputAdornment> } }} />
            <TextField type="number" label={t('activities.participantCount')} value={count} onChange={(e) => setCount(e.target.value)} />
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={details.trim().length < 2 || complete.isPending} onClick={() => complete.mutate()}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

export function ActivityDetailPage() {
  const { activityId = '' } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast, toastError, confirm } = useFeedback();
  const { data: a, isError } = useActivity(activityId);
  const [submitting, setSubmitting] = useState(false);
  const [completing, setCompleting] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: actKeys.activities });
  const cancel = useMutation({
    mutationFn: async () => (await api.post<Activity>(`/activities/${activityId}/cancel`, {})).data,
    onSuccess: () => { refresh(); toast(t('activities.cancelled')); },
    onError: toastError,
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/activities/${activityId}`),
    onSuccess: () => { refresh(); toast(t('activities.deleted')); navigate('/activities', { replace: true }); },
    onError: toastError,
  });
  if (isError) return <EmptyState title={t('activities.notFound')} />;
  if (!a) return <Skeleton variant="rounded" height={480} />;
  const amount = (v: string | null | undefined) => (v == null ? null : formatMoney(v));
  return (
    <>
      <PageHeader
        title={a.title}
        subtitle={`${a.code} · ${a.org_unit?.name ?? t('activities.parishLevel')}`}
        breadcrumbs={[{ label: t('nav.activities') }, { label: t('nav.activityList'), to: '/activities' }, { label: a.code }]}
        actions={
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {a.can.delete && <Button color="error" onClick={async () => {
              if (await confirm({ title: t('activities.deleteConfirm'), destructive: true })) remove.mutate();
            }}>{t('common.delete')}</Button>}
            {a.can.cancel && <Button color="inherit" onClick={async () => {
              if (await confirm({ title: t('activities.cancelConfirm'), destructive: true })) cancel.mutate();
            }}>{t('activities.cancel')}</Button>}
            {a.can.edit && <Button startIcon={<EditIcon />} component={RouterLink} to={`/activities/${a.id}/edit`}>{t('common.edit')}</Button>}
            {a.can.complete && <Button variant="outlined" onClick={() => setCompleting(true)}>{t('activities.recordCompletion')}</Button>}
            {a.can.submit && <Button variant="contained" startIcon={<SendIcon />} onClick={() => setSubmitting(true)}>
              {a.status === 'REWORK' ? t('activities.resubmit') : t('activities.submit')}</Button>}
          </Stack>
        }
      />
      {a.status === 'REWORK' && <Alert severity="warning" sx={{ mb: 2 }}>{t('activities.reworkBanner')}</Alert>}
      {a.status === 'IN_REVIEW' && <Alert severity="info" sx={{ mb: 2 }}>{t('activities.inReviewBanner')}</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('activities.details')} action={<StatusBadge status={a.status} />} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={{ xs: 6, md: 4 }}><Fact label={t('activities.date')}>{formatDate(a.activity_date)}{a.end_date ? ` – ${formatDate(a.end_date)}` : ''}</Fact></Grid>
                <Grid size={{ xs: 6, md: 4 }}><Fact label={t('activities.categoryLabel')}>{a.category ? <Chip size="small" label={t(`activities.category.${a.category}`)} /> : null}</Fact></Grid>
                <Grid size={{ xs: 12, md: 4 }}><Fact label={t('activities.location')}>{a.location}</Fact></Grid>
                <Grid size={{ xs: 6, md: 4 }}><Fact label={t('activities.responsible')}>{a.responsible}</Fact></Grid>
                <Grid size={{ xs: 6, md: 4 }}><Fact label={t('activities.recordedBy')}>{a.created_by}</Fact></Grid>
                <Grid size={{ xs: 12, md: 4 }}><Fact label={t('activities.participantCount')}>{a.participant_count?.toString()}</Fact></Grid>
                <Grid size={12}><Fact label={t('common.description')}>{a.description}</Fact></Grid>
              </Grid>
            </CardContent>
          </Card>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('activities.planAndOutcome')} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}><Fact label={t('activities.planned')}>{a.planned_details}</Fact></Grid>
                <Grid size={{ xs: 12, md: 6 }}><Fact label={t('activities.actual')}>{a.actual_details}</Fact></Grid>
                <Grid size={6}><Fact label={t('activities.plannedAmount')}>{amount(a.planned_amount)}</Fact></Grid>
                <Grid size={6}><Fact label={t('activities.actualAmount')}>{amount(a.actual_amount)}</Fact></Grid>
                {a.remarks && <Grid size={12}><Fact label={t('common.remarks')}>{a.remarks}</Fact></Grid>}
                {a.completed_at && <Grid size={12}><Typography variant="caption" color="text.secondary">{t('activities.completedOn', { date: formatDateTime(a.completed_at) })}</Typography></Grid>}
              </Grid>
            </CardContent>
          </Card>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('activities.participants')} subheader={a.participants.length ? t('activities.participantsN', { count: a.participants.length }) : undefined} />
            <CardContent sx={{ pt: 0 }}>
              {a.participants.length === 0 ? <Typography variant="body2" color="text.secondary">—</Typography> : (
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {a.participants.map((p, i) => <Chip key={i} variant={p.member_id ? 'filled' : 'outlined'} label={p.role ? `${p.name} · ${p.role}` : p.name} />)}
                </Stack>
              )}
            </CardContent>
          </Card>
          <ActionItemsCard activityId={a.id} canAdd={a.can.attach} />
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Stack spacing={2}>
            <ApprovalSection entityType="ACTIVITY" entityId={a.id} onChange={refresh} />
            <AttachmentsCard base={`/activities/${a.id}`} canAdd={a.can.attach} canRemove={a.can.edit} />
          </Stack>
        </Grid>
      </Grid>
      <SubmitDialog activity={a} open={submitting} onClose={() => setSubmitting(false)} />
      {completing && <CompleteDialog activity={a} open onClose={() => setCompleting(false)} />}
    </>
  );
}
