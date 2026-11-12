import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { Activity, Member } from '@/api/types';
import { PageHeader, useFeedback } from '@/design-system';
import { MemberPicker } from '@/features/people/pickers';
import { actKeys, CATEGORIES, today, useActivity } from './api';
import { OrgUnitSelect, PARISH } from './shared';

interface Participant { member_id: string | null; name: string; role: string }
interface Form {
  org_unit_id: string; title: string; category: string; description: string; activity_date: string; end_date: string;
  location: string; responsible_member_id: string | null; responsible_name: string; planned_details: string;
  actual_details: string; planned_amount: string; actual_amount: string; participant_count: string; remarks: string;
  participants: Participant[];
}

const EMPTY: Form = {
  org_unit_id: PARISH, title: '', category: '', description: '', activity_date: today(), end_date: '', location: '',
  responsible_member_id: null, responsible_name: '', planned_details: '', actual_details: '', planned_amount: '',
  actual_amount: '', participant_count: '', remarks: '', participants: [],
};

function fromActivity(a: Activity): Form {
  const s = (v: unknown) => (v == null ? '' : String(v));
  return {
    org_unit_id: a.org_unit?.id ?? PARISH, title: a.title, category: s(a.category), description: s(a.description),
    activity_date: a.activity_date, end_date: s(a.end_date), location: s(a.location),
    responsible_member_id: a.responsible_member?.id ?? null, responsible_name: s(a.responsible), planned_details: s(a.planned_details),
    actual_details: s(a.actual_details), planned_amount: s(a.planned_amount), actual_amount: s(a.actual_amount),
    participant_count: s(a.participant_count), remarks: s(a.remarks),
    participants: a.participants.map((p) => ({ member_id: p.member_id, name: p.name, role: p.role ?? '' })),
  };
}

function toBody(f: Form) {
  const n = (v: string) => (v.trim() === '' ? null : v.trim());
  return {
    org_unit_id: f.org_unit_id || null, title: f.title.trim(), category: n(f.category), description: n(f.description),
    activity_date: f.activity_date, end_date: n(f.end_date), location: n(f.location), responsible_member_id: f.responsible_member_id,
    responsible_name: n(f.responsible_name), planned_details: n(f.planned_details), actual_details: n(f.actual_details),
    planned_amount: n(f.planned_amount), actual_amount: n(f.actual_amount),
    participant_count: f.participant_count === '' ? null : Number(f.participant_count), remarks: n(f.remarks),
    participants: f.participants.map((p) => ({ member_id: p.member_id, name: p.name, role: n(p.role) })),
  };
}

export function ActivityFormPage() {
  const { activityId } = useParams();
  const editing = Boolean(activityId);
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const { data: existing } = useActivity(activityId);
  const [form, setForm] = useState<Form | null>(editing ? null : EMPTY);
  const [picked, setPicked] = useState<Member | null>(null);
  useEffect(() => { if (existing) setForm(fromActivity(existing)); }, [existing]);
  const save = useMutation({
    mutationFn: async (f: Form) => editing
      ? (await api.put<Activity>(`/activities/${activityId}`, toBody(f))).data
      : (await api.post<Activity>('/activities', toBody(f))).data,
    onSuccess: (a) => {
      void qc.invalidateQueries({ queryKey: actKeys.activities });
      toast(t('common.saved'));
      navigate(`/activities/${a.id}`, { replace: true });
    },
    onError: toastError,
  });
  if (!form) return <Skeleton variant="rounded" height={480} />;
  if (existing && !existing.can.edit) return <Alert severity="info">{t('activities.notEditable')}</Alert>;
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  const f = (k: keyof Form, label: string, props: object = {}) => (
    <TextField label={label} value={form[k] as string} onChange={(e) => set({ [k]: e.target.value } as Partial<Form>)} {...props} />
  );
  const money = { type: 'number', slotProps: { input: { startAdornment: <InputAdornment position="start">₹</InputAdornment> }, htmlInput: { min: 0, step: '0.01' } } };
  const date = { type: 'date', slotProps: { inputLabel: { shrink: true } } };
  const valid = form.title.trim().length >= 2 && form.activity_date && (!form.end_date || form.end_date >= form.activity_date);
  const title = editing ? t('activities.edit') : t('activities.new');
  return (
    <>
      <PageHeader title={title} subtitle={existing?.code}
        breadcrumbs={[{ label: t('nav.activities') }, { label: t('nav.activityList'), to: '/activities' }, { label: title }]}
        actions={
          <Stack direction="row" spacing={1}>
            <Button onClick={() => navigate(-1)}>{t('common.cancel')}</Button>
            <Button variant="contained" disabled={!valid || save.isPending} onClick={() => save.mutate(form)}>{t('activities.saveDraft')}</Button>
          </Stack>
        } />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('activities.details')} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={12}>{f('title', t('activities.name'), { required: true, autoFocus: !editing })}</Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <OrgUnitSelect permission="activity.create" autoSelect={!editing} value={form.org_unit_id}
                    onChange={(v) => setForm((cur) => (cur ? { ...cur, org_unit_id: v } : cur))}
                    disabled={existing ? existing.status !== 'DRAFT' : false} current={existing?.org_unit ?? null} />
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  {f('category', t('activities.categoryLabel'), { select: true, children: [
                    <MenuItem key="" value="">—</MenuItem>,
                    ...CATEGORIES.map((c) => <MenuItem key={c} value={c}>{t(`activities.category.${c}`)}</MenuItem>)] })}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>{f('activity_date', t('activities.date'), { ...date, required: true })}</Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>{f('end_date', t('activities.endDate'), date)}</Grid>
                <Grid size={{ xs: 12, md: 4 }}>{f('location', t('activities.location'))}</Grid>
                <Grid size={12}>{f('description', t('common.description'), { multiline: true, minRows: 2 })}</Grid>
              </Grid>
            </CardContent>
          </Card>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('activities.planAndOutcome')} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>{f('planned_details', t('activities.planned'), { multiline: true, minRows: 3 })}</Grid>
                <Grid size={{ xs: 12, md: 6 }}>{f('actual_details', t('activities.actual'), { multiline: true, minRows: 3, helperText: t('activities.actualHint') })}</Grid>
                <Grid size={{ xs: 12, sm: 4 }}>{f('planned_amount', t('activities.plannedAmount'), money)}</Grid>
                <Grid size={{ xs: 12, sm: 4 }}>{f('actual_amount', t('activities.actualAmount'), money)}</Grid>
                <Grid size={{ xs: 12, sm: 4 }}>{f('participant_count', t('activities.participantCount'), { type: 'number', slotProps: { htmlInput: { min: 0 } } })}</Grid>
                <Grid size={12}>{f('remarks', t('common.remarks'), { multiline: true, minRows: 2 })}</Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('activities.responsible')} />
            <CardContent sx={{ pt: 0 }}>
              <Stack spacing={1.5}>
                <MemberPicker label={t('activities.pickMember')} value={null}
                  onChange={(m) => m && set({ responsible_member_id: m.id, responsible_name: m.full_name })} />
                <TextField label={t('common.name')} value={form.responsible_name}
                  onChange={(e) => set({ responsible_name: e.target.value, responsible_member_id: null })}
                  helperText={form.responsible_member_id ? t('activities.fromRegister') : t('activities.orTypeName')} />
              </Stack>
            </CardContent>
          </Card>
          <Card>
            <CardHeader title={t('activities.participants')} subheader={t('activities.participantsHint')} />
            <CardContent sx={{ pt: 0 }}>
              <Stack spacing={1.5}>
                {form.participants.map((p, i) => (
                  <Stack key={i} direction="row" spacing={1} alignItems="center">
                    <TextField size="small" label={t('common.name')} value={p.name} sx={{ flex: 2 }}
                      onChange={(e) => set({ participants: form.participants.map((x, j) => (j === i ? { ...x, name: e.target.value, member_id: null } : x)) })} />
                    <TextField size="small" label={t('activities.role')} value={p.role} sx={{ flex: 1 }}
                      onChange={(e) => set({ participants: form.participants.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)) })} />
                    <IconButton aria-label={`${t('common.remove')} ${p.name}`} onClick={() => set({ participants: form.participants.filter((_, j) => j !== i) })}><DeleteIcon /></IconButton>
                  </Stack>
                ))}
                <MemberPicker label={t('activities.addMember')} value={picked} onChange={(m) => {
                  setPicked(null);
                  if (m && !form.participants.some((p) => p.member_id === m.id)) set({ participants: [...form.participants, { member_id: m.id, name: m.full_name, role: '' }] });
                }} />
                <div><Button size="small" startIcon={<AddIcon />} onClick={() => set({ participants: [...form.participants, { member_id: null, name: '', role: '' }] })}>{t('activities.addGuest')}</Button></div>
                {form.participants.length > 0 && <Typography variant="caption" color="text.secondary">{t('activities.participantsN', { count: form.participants.length })}</Typography>}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
