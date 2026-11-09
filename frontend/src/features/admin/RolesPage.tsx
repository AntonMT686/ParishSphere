import AddIcon from '@mui/icons-material/AddModeratorOutlined';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid2';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { api } from '@/api/client';
import type { Role } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { applyServerErrors, FormSelect, FormTextField, PageHeader, useFeedback } from '@/design-system';
import { useRoles } from './api';

const schema = z.object({
  code: z.string().trim().min(2).max(50).regex(/^[A-Za-z][A-Za-z0-9_]*$/, 'Letters, digits and _'),
  name: z.string().trim().min(2).max(100),
  description: z.string().max(1000),
  scope_type: z.enum(['PARISH', 'ORG_UNIT', 'ANY']),
});
type Values = z.infer<typeof schema>;

function CreateRoleDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { toastError } = useFeedback();
  const { control, handleSubmit, setError, reset } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { code: '', name: '', description: '', scope_type: 'PARISH' },
  });
  const create = useMutation({
    mutationFn: async (v: Values) => (await api.post<Role>('/roles', { ...v, permissions: [] })).data,
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ['roles'] });
      reset();
      onClose();
      navigate(`/admin/roles/${r.id}`);
    },
    onError: (e) => {
      if (!applyServerErrors(e, setError, ['code', 'name', 'description', 'scope_type'])) toastError(e);
    },
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form noValidate onSubmit={handleSubmit((v) => create.mutate(v))}>
        <DialogTitle>{t('roles.new')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <FormTextField control={control} name="name" label={t('common.name')} autoFocus required />
            <FormTextField control={control} name="code" label={t('roles.code')} required
              slotProps={{ htmlInput: { style: { textTransform: 'uppercase' } } }} />
            <FormSelect control={control} name="scope_type" label={t('roles.scope')}
              options={(['PARISH', 'ORG_UNIT', 'ANY'] as const).map((s) => ({ value: s, label: t(`roles.scope_${s}`) }))} />
            <FormTextField control={control} name="description" label={t('roles.description')} multiline minRows={2} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={create.isPending}>
            {t('common.create')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

export function RolesPage() {
  const { t } = useTranslation();
  const { data, isLoading } = useRoles();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader
        title={t('roles.title')}
        subtitle={t('roles.subtitle')}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('roles.title') }]}
        actions={
          <PermissionGate anyOf="role.manage">
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreating(true)}>
              {t('roles.new')}
            </Button>
          </PermissionGate>
        }
      />
      <Grid container spacing={2}>
        {isLoading &&
          Array.from({ length: 6 }, (_, i) => (
            <Grid key={i} size={{ xs: 12, sm: 6, lg: 4 }}>
              <Skeleton variant="rounded" height={130} />
            </Grid>
          ))}
        {(data ?? []).map((r) => (
          <Grid key={r.id} size={{ xs: 12, sm: 6, lg: 4 }}>
            <Card sx={{ height: '100%' }}>
              <CardActionArea component={RouterLink} to={`/admin/roles/${r.id}`} sx={{ height: '100%' }}>
                <CardContent>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <Typography variant="h4" sx={{ flexGrow: 1 }}>
                      {r.name}
                    </Typography>
                    <Chip size="small" variant="outlined" label={r.is_system ? t('roles.system') : t('roles.custom')} />
                  </Stack>
                  <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40 }}>
                    {r.description}
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
                    <Chip size="small" label={t(`roles.scope_${r.scope_type}`)} />
                    <Chip size="small" label={`${r.permission_count} ${t('roles.permissions').toLowerCase()}`} />
                    <Chip size="small" color={r.active_users ? 'primary' : 'default'} label={`${r.active_users} ${t('roles.activeUsers').toLowerCase()}`} />
                  </Stack>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
      <CreateRoleDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
