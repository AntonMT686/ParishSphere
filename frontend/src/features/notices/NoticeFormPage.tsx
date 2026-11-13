import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import MenuItem from '@mui/material/MenuItem';
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { Notice, OrgUnit } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { PageHeader, useFeedback } from '@/design-system';
import { toLocalInput } from '@/features/activities/api';
import { OrgUnitSelect, PARISH } from '@/features/activities/shared';
import { OrgUnitPicker } from '@/features/org/pickers';
import { CATEGORIES, noticeKeys, useNotice } from './api';

type Unit = Pick<OrgUnit, 'id' | 'name' | 'code'>;
interface Form {
  title: string; title_local: string; category: string; body: string; body_local: string; org_unit_id: string;
  audience_all: boolean; units: Unit[]; is_important: boolean; is_public: boolean; publish_at: string; expires_at: string;
}
const EMPTY: Form = { title: '', title_local: '', category: 'WEEKLY', body: '', body_local: '', org_unit_id: PARISH, audience_all: true,
  units: [], is_important: false, is_public: true, publish_at: '', expires_at: '' };

export function NoticeFormPage() {
  const { noticeId } = useParams();
  const editing = Boolean(noticeId);
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const can = useCan();
  const { toast, toastError } = useFeedback();
  const { data: existing } = useNotice(noticeId);
  const [form, setForm] = useState<Form | null>(editing ? null : EMPTY);
  const [picker, setPicker] = useState<Unit | null>(null);
  useEffect(() => {
    if (existing) {
      setForm({
        title: existing.title, title_local: existing.title_local ?? '', category: existing.category, body: existing.body,
        body_local: existing.body_local ?? '', org_unit_id: existing.org_unit?.id ?? PARISH, audience_all: existing.audience_all,
        units: existing.audience.map((a) => ({ id: a.id, name: a.name, code: '' })), is_important: existing.is_important,
        is_public: existing.is_public, publish_at: toLocalInput(existing.publish_at), expires_at: toLocalInput(existing.expires_at),
      });
    }
  }, [existing]);
  const save = useMutation({
    mutationFn: async (f: Form) => {
      const body = {
        title: f.title, title_local: f.title_local || null, category: f.category, body: f.body, body_local: f.body_local || null,
        org_unit_id: f.org_unit_id || null, audience_all: f.audience_all, audience_org_units: f.audience_all ? [] : f.units.map((u) => u.id),
        is_important: f.is_important, is_public: f.audience_all && f.is_public, publish_at: f.publish_at || null, expires_at: f.expires_at || null,
      };
      return editing ? (await api.put<Notice>(`/notices/${noticeId}`, body)).data : (await api.post<Notice>('/notices', body)).data;
    },
    onSuccess: (n) => { qc.setQueryData([...noticeKeys.all, n.id], n); void qc.invalidateQueries({ queryKey: noticeKeys.all }); toast(t('common.saved')); navigate(`/notices/${n.id}`, { replace: true }); },
    onError: toastError,
  });
  if (!form) return <Skeleton variant="rounded" height={480} />;
  if (existing && !existing.can.edit) return <Alert severity="info">{t('activities.notEditable')}</Alert>;
  const set = (p: Partial<Form>) => setForm({ ...form, ...p });
  const valid = form.title.trim().length >= 3 && form.body.trim().length >= 3 && (form.audience_all || form.units.length > 0)
    && (!form.publish_at || !form.expires_at || form.expires_at > form.publish_at);
  const title = editing ? t('notices.edit') : t('notices.new');
  return (
    <>
      <PageHeader title={title} breadcrumbs={[{ label: t('nav.content') }, { label: t('nav.notices'), to: '/notices' }, { label: title }]}
        actions={<Stack direction="row" spacing={1}><Button onClick={() => navigate(-1)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!valid || save.isPending} onClick={() => save.mutate(form)}>{t('activities.saveDraft')}</Button></Stack>} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('notices.content')} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 8 }}><TextField label={t('notices.title')} value={form.title} onChange={(e) => set({ title: e.target.value })} required autoFocus={!editing} /></Grid>
                <Grid size={{ xs: 12, md: 4 }}>
                  <TextField select label={t('notices.categoryLabel')} value={form.category} onChange={(e) => set({ category: e.target.value, is_important: e.target.value === 'EMERGENCY' || form.is_important })}>
                    {CATEGORIES.map((c) => <MenuItem key={c} value={c}>{t(`notices.category.${c}`)}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid size={12}><TextField label={t('notices.body')} value={form.body} onChange={(e) => set({ body: e.target.value })} multiline minRows={6} required /></Grid>
                <Grid size={12}><TextField label={t('notices.titleLocal')} value={form.title_local} onChange={(e) => set({ title_local: e.target.value })} /></Grid>
                <Grid size={12}><TextField label={t('notices.bodyLocal')} value={form.body_local} onChange={(e) => set({ body_local: e.target.value })} multiline minRows={4} helperText={t('notices.localHint')} /></Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('notices.when')} />
            <CardContent sx={{ pt: 0 }}>
              <Stack spacing={2}>
                <TextField type="datetime-local" label={t('notices.publishAt')} value={form.publish_at} onChange={(e) => set({ publish_at: e.target.value })}
                  slotProps={{ inputLabel: { shrink: true } }} helperText={t('notices.publishHint')} />
                <TextField type="datetime-local" label={t('notices.expiresAt')} value={form.expires_at} onChange={(e) => set({ expires_at: e.target.value })}
                  slotProps={{ inputLabel: { shrink: true } }} error={Boolean(form.publish_at && form.expires_at && form.expires_at <= form.publish_at)} />
                <FormControlLabel control={<Switch checked={form.is_important} disabled={form.category === 'EMERGENCY'} onChange={(e) => set({ is_important: e.target.checked })} />} label={t('notices.markImportant')} />
              </Stack>
            </CardContent>
          </Card>
          <Card>
            <CardHeader title={t('notices.audience')} />
            <CardContent sx={{ pt: 0 }}>
              <Stack spacing={1.5}>
                <RadioGroup value={form.audience_all ? 'all' : 'some'} onChange={(e) => set({ audience_all: e.target.value === 'all' })}>
                  <FormControlLabel value="all" control={<Radio />} label={t('notices.everyone')} />
                  <FormControlLabel value="some" control={<Radio />} label={t('notices.someOrgs')} />
                </RadioGroup>
                {!form.audience_all && (
                  <>
                    <OrgUnitPicker label={t('notices.addOrg')} value={picker} onChange={(u) => {
                      setPicker(null);
                      if (u && !form.units.some((x) => x.id === u.id)) set({ units: [...form.units, u] });
                    }} />
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {form.units.map((u) => <Chip key={u.id} label={u.name} onDelete={() => set({ units: form.units.filter((x) => x.id !== u.id) })} />)}
                    </Stack>
                  </>
                )}
                <FormControlLabel control={<Switch checked={form.audience_all && form.is_public} disabled={!form.audience_all} onChange={(e) => set({ is_public: e.target.checked })} />}
                  label={t('notices.publicPortal')} />
                {can('notice.create') && (
                  <OrgUnitSelect permission="notice.create" value={form.org_unit_id} onChange={(v) => setForm((c) => (c ? { ...c, org_unit_id: v } : c))}
                    current={existing?.org_unit ?? null} helperText={t('notices.preparedByHint')} label={t('notices.preparedBy')} />
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
