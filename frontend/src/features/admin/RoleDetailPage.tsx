import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import { useCan } from '@/auth/authStore';
import { PageHeader, useFeedback } from '@/design-system';
import { usePermissionCatalog, useRole } from './api';

export function RoleDetailPage() {
  const { t } = useTranslation();
  const { roleId = '' } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const can = useCan();
  const editable = can('role.manage');
  const { toast, toastError, confirm } = useFeedback();
  const { data: role } = useRole(roleId);
  const { data: catalog } = usePermissionCatalog();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (role) setSelected(new Set(role.permissions));
  }, [role]);
  const dirty = useMemo(
    () => role !== undefined && (selected.size !== role.permissions.length || role.permissions.some((p) => !selected.has(p))),
    [role, selected],
  );

  const save = useMutation({
    mutationFn: () => api.patch(`/roles/${roleId}`, { permissions: [...selected].sort() }),
    onSuccess: () => {
      toast(t('common.saved'));
      void qc.invalidateQueries({ queryKey: ['roles'] });
    },
    onError: toastError,
  });

  const toggle = (code: string, on: boolean) =>
    setSelected((s) => {
      const next = new Set(s);
      if (on) next.add(code);
      else next.delete(code);
      return next;
    });

  if (!role || !catalog) return <Skeleton variant="rounded" height={400} />;

  return (
    <>
      <PageHeader
        title={role.name}
        subtitle={role.description ?? undefined}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('roles.title'), to: '/admin/roles' }, { label: role.name }]}
        actions={
          editable && (
            <Stack direction="row" spacing={1}>
              {!role.is_system && (
                <Button
                  color="error"
                  onClick={async () => {
                    if (!(await confirm({ title: t('common.delete'), message: t('roles.deleteConfirm'), destructive: true }))) return;
                    try {
                      await api.delete(`/roles/${roleId}`);
                      void qc.invalidateQueries({ queryKey: ['roles'] });
                      navigate('/admin/roles');
                    } catch (e) {
                      toastError(e);
                    }
                  }}
                >
                  {t('common.delete')}
                </Button>
              )}
              <Button variant="contained" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
                {t('roles.savePermissions')}
              </Button>
            </Stack>
          )
        }
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <Chip label={role.code} />
        <Chip label={t(`roles.scope_${role.scope_type}`)} />
        <Chip color="primary" label={`${selected.size} ${t('roles.permissions').toLowerCase()}`} />
      </Stack>
      <Grid container spacing={2}>
        {catalog.map((m) => {
          const codes = m.permissions.map((p) => p.code);
          const all = codes.every((c) => selected.has(c));
          const some = codes.some((c) => selected.has(c));
          return (
            <Grid key={m.module} size={{ xs: 12, md: 6, xl: 4 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={all}
                        indeterminate={some && !all}
                        disabled={!editable}
                        onChange={(_, on) => codes.forEach((c) => toggle(c, on))}
                      />
                    }
                    label={<Typography variant="h4" sx={{ textTransform: 'capitalize' }}>{m.module.replace(/_/g, ' ')}</Typography>}
                  />
                  <Stack sx={{ pl: 3 }}>
                    {m.permissions.map((p) => (
                      <FormControlLabel
                        key={p.code}
                        control={<Checkbox size="small" checked={selected.has(p.code)} disabled={!editable} onChange={(_, on) => toggle(p.code, on)} />}
                        label={<Typography variant="body2">{p.description}</Typography>}
                      />
                    ))}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    </>
  );
}
