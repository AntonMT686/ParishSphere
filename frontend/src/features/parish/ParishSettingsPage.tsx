import DeleteIcon from '@mui/icons-material/DeleteOutline';
import UploadIcon from '@mui/icons-material/UploadFileOutlined';
import Alert from '@mui/material/Alert';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid2';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import type { ParishProfile } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { PageHeader, useFeedback } from '@/design-system';
import { CURRENCIES, parishKeys, TIMEZONES, useParishProfile } from './api';

const TEXT_FIELDS = ['name', 'name_local', 'patron_saint', 'established_on', 'about', 'address_line1', 'address_line2', 'city', 'state',
  'postal_code', 'phone', 'email', 'website', 'primary_color', 'default_language', 'currency', 'timezone'] as const;
type Form = Record<(typeof TEXT_FIELDS)[number], string> & { fy_start_month: number };

function toForm(p: ParishProfile): Form {
  const f = Object.fromEntries(TEXT_FIELDS.map((k) => [k, (p as unknown as Record<string, string | null>)[k] ?? ''])) as unknown as Form;
  f.fy_start_month = p.fy_start_month;
  return f;
}

export function ParishSettingsPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const can = useCan();
  const editable = can('settings.update');
  const { toast, toastError, confirm } = useFeedback();
  const { data: profile } = useParishProfile();
  const [form, setForm] = useState<Form | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (profile) setForm(toForm(profile)); }, [profile]);

  const refresh = (p: ParishProfile) => {
    qc.setQueryData(parishKeys.profile, p);
    void qc.invalidateQueries({ queryKey: ['tenant'] }); // branding: name, logo, colour in the shell
  };
  const save = useMutation({
    mutationFn: async (f: Form) => {
      const body: Record<string, unknown> = { ...f };
      for (const k of TEXT_FIELDS) if (body[k] === '' && !['name', 'default_language', 'currency', 'timezone'].includes(k)) body[k] = null;
      return (await api.patch<ParishProfile>('/parish/profile', body)).data;
    },
    onSuccess: (p) => { refresh(p); toast(t('common.saved')); },
    onError: toastError,
  });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return (await api.post<ParishProfile>('/parish/profile/logo', fd)).data;
    },
    onSuccess: (p) => { refresh(p); toast(t('common.saved')); },
    onError: toastError,
  });
  const removeLogo = useMutation({
    mutationFn: async () => (await api.delete<ParishProfile>('/parish/profile/logo')).data,
    onSuccess: (p) => { refresh(p); toast(t('common.saved')); },
    onError: toastError,
  });

  if (!profile || !form) return <Skeleton variant="rounded" height={420} />;
  const field = (k: keyof Form, label: string, props: object = {}) => (
    <TextField label={label} value={form[k]} disabled={!editable}
      onChange={(e) => setForm({ ...form, [k]: k === 'fy_start_month' ? Number(e.target.value) : e.target.value })} {...props} />
  );
  const months = Array.from({ length: 12 }, (_, i) => new Date(2000, i, 1).toLocaleString(i18n.language === 'ta' ? 'ta-IN' : 'en-IN', { month: 'long' }));

  return (
    <>
      <PageHeader
        title={t('nav.settings')}
        subtitle={`${profile.code} · ${profile.diocese_name}`}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('nav.settings') }]}
        actions={editable && (
          <Button variant="contained" disabled={save.isPending || !form.name.trim()} onClick={() => save.mutate(form)}>{t('common.save')}</Button>
        )}
      />
      {!editable && <Alert severity="info" sx={{ mb: 2 }}>{t('parish.readOnly')}</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('parish.details')} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>{field('name', t('parish.name'), { required: true })}</Grid>
                <Grid size={{ xs: 12, md: 6 }}>{field('name_local', t('parish.nameLocal'))}</Grid>
                <Grid size={{ xs: 12, md: 6 }}>{field('patron_saint', t('parish.patronSaint'))}</Grid>
                <Grid size={{ xs: 12, md: 6 }}>{field('established_on', t('org.established'), { type: 'date', slotProps: { inputLabel: { shrink: true } } })}</Grid>
                <Grid size={12}>{field('about', t('parish.about'), { multiline: true, minRows: 3 })}</Grid>
              </Grid>
            </CardContent>
          </Card>
          <Card>
            <CardHeader title={t('parish.contact')} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={12}>{field('address_line1', t('people.address1'))}</Grid>
                <Grid size={12}>{field('address_line2', t('people.address2'))}</Grid>
                <Grid size={{ xs: 12, md: 5 }}>{field('city', t('people.city'))}</Grid>
                <Grid size={{ xs: 12, md: 4 }}>{field('state', t('people.state'))}</Grid>
                <Grid size={{ xs: 12, md: 3 }}>{field('postal_code', t('people.postalCode'))}</Grid>
                <Grid size={{ xs: 12, md: 4 }}>{field('phone', t('common.phone'))}</Grid>
                <Grid size={{ xs: 12, md: 4 }}>{field('email', t('common.email'))}</Grid>
                <Grid size={{ xs: 12, md: 4 }}>{field('website', t('parish.website'), { placeholder: 'https://' })}</Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('parish.branding')} />
            <CardContent sx={{ pt: 0 }}>
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
                <Avatar src={profile.logo_url ?? '/favicon.svg'} variant="rounded" sx={{ width: 72, height: 72, bgcolor: 'background.default' }} alt={t('parish.logo')} />
                {editable && (
                  <Stack spacing={1}>
                    <input ref={fileRef} type="file" accept="image/png,image/jpeg" hidden aria-label={t('parish.logo')}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ''; }} />
                    <Button startIcon={<UploadIcon />} onClick={() => fileRef.current?.click()} disabled={upload.isPending}>{t('parish.uploadLogo')}</Button>
                    {profile.logo_url && (
                      <Button color="error" startIcon={<DeleteIcon />} onClick={async () => {
                        if (await confirm({ title: t('parish.removeLogo'), destructive: true })) removeLogo.mutate();
                      }}>{t('parish.removeLogo')}</Button>
                    )}
                  </Stack>
                )}
              </Stack>
              <Typography variant="caption" color="text.secondary" component="p" sx={{ mb: 2 }}>{t('parish.logoHint')}</Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                <Box component="input" type="color" value={form.primary_color || '#2F3E9E'} disabled={!editable}
                  aria-label={t('parish.primaryColor')}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, primary_color: e.target.value.toUpperCase() })}
                  sx={{ width: 48, height: 40, border: 0, p: 0, bgcolor: 'transparent', cursor: editable ? 'pointer' : 'default' }} />
                {field('primary_color', t('parish.primaryColor'), { placeholder: '#2F3E9E' })}
                {form.primary_color && editable && <Button onClick={() => setForm({ ...form, primary_color: '' })}>{t('parish.resetColor')}</Button>}
              </Stack>
            </CardContent>
          </Card>
          <Card>
            <CardHeader title={t('parish.regional')} />
            <CardContent sx={{ pt: 0 }}>
              <Stack spacing={2}>
                {field('fy_start_month', t('parish.fyStart'), { select: true, helperText: t('parish.fyHint'),
                  children: months.map((m, i) => <MenuItem key={m} value={i + 1}>{m}</MenuItem>) })}
                {field('currency', t('parish.currency'), { select: true, children: CURRENCIES.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>) })}
                {field('default_language', t('parish.language'), { select: true, children: [
                  <MenuItem key="en" value="en">English</MenuItem>, <MenuItem key="ta" value="ta">தமிழ்</MenuItem>] })}
                {field('timezone', t('parish.timezone'), { select: true, children: TIMEZONES.map((z) => <MenuItem key={z} value={z}>{z}</MenuItem>) })}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
